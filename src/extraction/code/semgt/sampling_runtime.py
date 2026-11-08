"""Explicit CPU sampler CLI runtime; preserve the installed conda C++ ABI."""
import os,sys,tempfile
from pathlib import Path


def environment(python=None):
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    executable=Path(python or sys.executable).resolve();library=executable.parent.parent/'lib/libstdc++.so.6'
    if library.is_file():
        old=env.get('LD_PRELOAD','')
        if str(library) not in old.replace(':',' ').split():env['LD_PRELOAD']=str(library)+(':'+old if old else '')
    env.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'lanegt-maptr-matplotlib'))
    return env


def ensure_cpu_process():
    """Call from an explicit sampling CLI, before creating any output directory."""
    env=environment()
    if env.get('LD_PRELOAD','')!=os.environ.get('LD_PRELOAD',''):
        os.execve(sys.executable,[sys.executable,'-B']+sys.argv,env)
    os.environ.update({k:env[k] for k in ['CUDA_VISIBLE_DEVICES','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','PYTHONDONTWRITEBYTECODE','MPLCONFIGDIR']})
