"""Regenerate machine-readable contracts and MySQL DDL without connecting to a database."""
import json
from pathlib import Path
from sqlalchemy import create_mock_engine
from sqlalchemy.schema import CreateTable
from api import create_app
from worker import create_worker
from contracts import ResultInput
from schema import metadata

def main():
    root = Path(__file__).resolve().parents[1] / 'docs'
    engine = create_mock_engine('mysql+pymysql://', lambda *args, **kwargs: None)
    app = create_app(engine, 'documentation-only-placeholder', with_auth=True)
    worker = create_worker(engine, 'documentation-only-placeholder')
    outputs = {'openapi.json': app.openapi(), 'worker_openapi.json': worker.openapi(),
               'result_json_schema.json': ResultInput.model_json_schema()}
    for name, value in outputs.items():
        (root/'api'/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    ddl = '\n\n'.join(str(CreateTable(t).compile(dialect=engine.dialect))+';'
                        for t in metadata.sorted_tables)
    (root/'database/schema.sql').write_text('\n'.join(line.rstrip() for line in ddl.splitlines())+'\n',encoding='utf-8')
    dictionary=['# 백엔드 데이터 사전','','자동 생성 기준: 실제 SQLAlchemy metadata.','']
    erd=['# 백엔드 ERD','','```mermaid','erDiagram']
    for table in metadata.sorted_tables:
        dictionary += ['## '+table.name,'','| 필드 | DB 타입 | 필수 | 키·관계 | 기본값 |',
                       '|---|---|---|---|---|']
        erd.append('    '+table.name+' {')
        for column in table.columns:
            flags=','.join(flag for flag,yes in [('PK',column.primary_key),('UK',column.unique),
                                                  ('FK',bool(column.foreign_keys))] if yes)
            refs=', '.join(sorted(f.target_fullname for f in column.foreign_keys))
            default=column.default.arg if column.default is not None else ''
            if callable(default):default=getattr(default,'__name__','callable')+'()'
            dictionary.append(f'| {column.name} | {column.type} | {"아니오" if column.nullable else "예"} | {flags} {refs} | {default} |')
            typ=str(column.type.compile(dialect=engine.dialect)).replace(' ','_').replace('(','_').replace(')','')
            erd.append(f'        {typ} {column.name}'+(' '+flags if flags else ''))
        erd.append('    }')
        for fk in sorted(table.foreign_keys,key=lambda f:f.parent.name):
            unique=fk.parent.unique or (fk.parent.primary_key and len(table.primary_key.columns)==1)
            unique=unique or any(con.__class__.__name__=='UniqueConstraint' and len(con.columns)==1
                                 and fk.parent.name in con.columns for con in table.constraints)
            erd.append(f'    {fk.column.table.name} '+('||--o|' if unique else '||--o{')+f' {table.name} : "{fk.parent.name}"')
        for con in sorted(table.constraints,key=lambda c:c.name or ''):
            if con.__class__.__name__ in ['UniqueConstraint','CheckConstraint']:
                dictionary.append('- '+str(con.name)+': '+(str(con.sqltext) if hasattr(con,'sqltext') else ', '.join(c.name for c in con.columns)))
        dictionary.append('')
    erd += ['```','']
    (root/'database/data-dictionary.md').write_text('\n'.join(dictionary),encoding='utf-8')
    (root/'database/erd.md').write_text('\n'.join(erd),encoding='utf-8')
    print(f'Contracts and DDL regenerated without DB access: {len(metadata.tables)} tables')

if __name__ == '__main__':
    main()
