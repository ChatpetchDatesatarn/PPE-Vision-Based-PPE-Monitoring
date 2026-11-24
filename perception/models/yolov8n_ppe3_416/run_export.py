import sys, runpy, inspect, torch
_orig = torch.onnx.export
def _export(*a, **k):
    if 'dynamo' in inspect.signature(_orig).parameters:
        k.setdefault('dynamo', False)
    return _orig(*a, **k)
torch.onnx.export = _export
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
