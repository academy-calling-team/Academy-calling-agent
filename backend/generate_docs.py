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
    print(f'Contracts and DDL regenerated without DB access: {len(metadata.tables)} tables')

if __name__ == '__main__':
    main()
