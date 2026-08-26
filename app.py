"""
Wrapper de compatibilidade para redirecionar execuções legadas de app.py para dashboard.py.
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("dashboard", run_name="__main__")
