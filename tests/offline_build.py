"""Build with network sockets and DB imports explicitly forbidden."""
import builtins
from pathlib import Path
import runpy
import socket
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
real_import=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in {'db','psycopg2','stephanos_db'}:
        raise AssertionError('Database import attempted: '+name)
    return real_import(name,*args,**kwargs)
def denied(*args,**kwargs): raise AssertionError('Network access attempted')
builtins.__import__=guarded
socket.socket=denied
sys.argv=[str(root/'generate_site.py'),*sys.argv[1:]]
runpy.run_path(str(root/'generate_site.py'),run_name='__main__')
