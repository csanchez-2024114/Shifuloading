import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['MONGO_URI'] = 'mongodb://localhost:27017/shifuai'
from main import app
import uvicorn
import traceback

try:
    uvicorn.run(app, host='127.0.0.1', port=5000, log_level='info')
except Exception as e:
    traceback.print_exc()
    print('UVICORN_ERROR', e)
