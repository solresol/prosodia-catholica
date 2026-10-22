"""Explicit tiny local integration runner; never connects to production.

Uses installed PostgreSQL 16 binaries and a private socket-only cluster under
/tmp. Requires psycopg2. Run only when resource headroom permits.
"""
from pathlib import Path
import getpass
import os
import subprocess
import tempfile
import psycopg2


def main():
    binary=Path('/usr/lib/postgresql/16/bin')
    source=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='prosodia-pg-test-',dir='/tmp') as tmp:
        root=Path(tmp)
        data=root/'data'
        def run(args, **kwargs):
            return subprocess.run([str(x) for x in args],check=True,**kwargs)
        run([binary/'initdb','-D',data,'--no-locale','--encoding=UTF8','--auth-local=peer','--auth-host=reject'],stdout=subprocess.DEVNULL)
        started=False
        try:
            options=f"-F -c listen_addresses='' -c unix_socket_directories='{root}' -c shared_buffers=8MB -c max_connections=8 -c max_wal_senders=0 -c wal_level=minimal -c autovacuum=off -p 65432"
            try:
                run([binary/'pg_ctl','-D',data,'-l',root/'server.log','-o',options,'-w','start'],stdout=subprocess.DEVNULL)
            except Exception:
                print((root/'server.log').read_text())
                raise
            started=True
            conn=psycopg2.connect(host=str(root),port=65432,dbname='postgres',user=getpass.getuser())
            conn.autocommit=True
            with conn.cursor() as cur:
                cur.execute('CREATE DATABASE prosodia_disposable')
            conn.close()
            dsn=f'host={root} port=65432 dbname=prosodia_disposable user={getpass.getuser()}'
            env=dict(os.environ,PROSODIA_TEST_DSN=dsn)
            run(['python3','-m','unittest','discover','-s','tests','-p','test_import_postgres.py','-v'],cwd=source,env=env)
        finally:
            if started or (data/'postmaster.pid').exists():
                run([binary/'pg_ctl','-D',data,'-m','fast','-w','stop'],stdout=subprocess.DEVNULL)
        print('Disposable PostgreSQL stopped; temporary cluster removed on exit. No production connection made.')

if __name__ == "__main__":
    main()
