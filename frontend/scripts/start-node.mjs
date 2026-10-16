import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
if (existsSync('.env.local')) process.loadEnvFile('.env.local');
if (!process.env.ACADEMY_BACKEND_URL || !process.env.FRONTEND_ORIGIN) throw new Error('Copy .env.node.example to .env.local first');
const origin=new URL(process.env.FRONTEND_ORIGIN);
if (!['127.0.0.1','localhost'].includes(origin.hostname)) throw new Error('Local launcher requires a localhost frontend origin');
const child=spawn(process.execPath,['.next/standalone/server.js'],{stdio:'inherit',env:{...process.env,HOSTNAME:'127.0.0.1',PORT:origin.port||'3000'}});
child.on('exit',code=>{process.exitCode=code??1;});
for (const signal of ['SIGINT','SIGTERM']) process.on(signal,()=>child.kill(signal));
