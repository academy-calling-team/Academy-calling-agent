#!/usr/bin/env python3
"""EC2 operator prerequisite. Check by default; grant table-scoped DELETE only with --apply.

No credentials are accepted, printed, or changed. Uses the existing DB container's
root environment at runtime. Does not promote application users to administrators.
"""
import argparse
import json
import os
import re
import subprocess

TABLES = (
    'w5_result_corrections', 'w5_answers', 'w5_events', 'w6_provider_inbox', 'w6_provider_calls',
    'w5_dispatch_outbox', 'w5_delivery_leases', 'w5_mock_worker_receipts', 'w5_results',
    'w6_review_holds', 'w6_review_actions', 'w6_fallback_tasks', 'w5_calls', 'w5_questions',
    'w5_inquiries', 'w5_academy_classes', 'w5_academy_call_hours', 'w5_academy_setting_states',
    'w5_academy_policies', 'w6_academy_profiles', 'w5_academies',
)


def grant_statements(user, host, database):
    if database != 'team8_dev' or not re.fullmatch(r'[A-Za-z0-9_]+', user) or user == 'root':
        raise ValueError('Expected the existing non-root application identity in team8_dev')
    if not re.fullmatch(r'[A-Za-z0-9_.%:-]+', host):
        raise ValueError('Unsupported MySQL account host')
    return [f"GRANT DELETE ON `team8_dev`.`{table}` TO '{user}'@'{host}'" for table in TABLES]


def mysql(sql):
    process = subprocess.run(['docker', 'exec', '-i', 'team8-mysql', 'sh', '-c',
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --batch --skip-column-names -uroot team8_dev'],
        input=sql, text=True, capture_output=True)
    if process.returncode:
        raise RuntimeError('DB permission operation failed; inspect privately on the host')
    return process.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Grant DELETE only on the listed management tables')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Run with sudo on the existing EC2 host')
    code = """import json
from local_runtime import local_engine
e=local_engine()
with e.connect() as c:
 print(json.dumps(list(c.exec_driver_sql('SELECT CURRENT_USER(), DATABASE()').one())))
e.dispose()
"""
    process = subprocess.run(['docker','exec','team8-shared-api','python','-c',code],text=True,capture_output=True)
    if process.returncode:
        raise RuntimeError('Cannot identify the current application DB account')
    account, database = json.loads(process.stdout)
    user, host = account.rsplit('@',1)
    statements = grant_statements(user,host,database)
    grantee = "'"+user+"'@'"+host+"'"
    escaped = "'"+grantee.replace("'","''")+"'"
    def missing():
        global_delete = int(mysql("SELECT COUNT(*) FROM information_schema.USER_PRIVILEGES WHERE PRIVILEGE_TYPE='DELETE' AND GRANTEE="+escaped))
        schema_delete = int(mysql("SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA='team8_dev' AND PRIVILEGE_TYPE='DELETE' AND GRANTEE="+escaped))
        if global_delete or schema_delete:
            return []
        actual = set(mysql("SELECT TABLE_NAME FROM information_schema.TABLE_PRIVILEGES WHERE TABLE_SCHEMA='team8_dev' AND PRIVILEGE_TYPE='DELETE' AND GRANTEE="+escaped).splitlines())
        return [name for name in TABLES if name not in actual]
    before = missing()
    if args.apply:
        # Only additive table-level grants; no database-wide grant or account/credential changes.
        for statement in statements:
            mysql(statement+';')
    after = missing()
    result = dict(status='ready' if not after else 'permission-preparation-required',
        applied=args.apply, missing_before=before, missing_after=after, required_tables=list(TABLES),
        member_accounts_unchanged=True, database_rows_changed=False)
    print(json.dumps(result))
    if args.apply and after:
        raise RuntimeError('Management permissions remain incomplete')


if __name__ == '__main__':
    main()
