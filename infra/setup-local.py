"""Create ignored settings for a local isolated mock environment; print no credentials."""
from pathlib import Path
import secrets
root=Path(__file__).resolve().parents[1]
target=root/'.env'
if target.exists():
    raise SystemExit('Repository .env exists. Keep it and review compose settings; no overwrite performed.')
values={'TEAM8_MYSQL_ROOT_PASSWORD':secrets.token_hex(24),'TEAM8_MYSQL_PASSWORD':secrets.token_hex(24),'TEAM8_INTERNAL_KEY':secrets.token_hex(24)}
target.write_text(''.join(k+'='+v+'\n' for k,v in values.items()),encoding='utf-8')
print('Local Docker settings created in ignored .env. No shared server settings used.')
