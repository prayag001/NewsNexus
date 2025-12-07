import subprocess, json
p = subprocess.Popen([
    'C:\\Swdtools\\conda_envs\\python_3.13\\python.exe',
    'c:\\Swdtools\\NewsNexus\\main.py'
], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
req1 = json.dumps({
    'jsonrpc':'2.0',
    'id':1,
    'method':'initialize',
    'params':{
        'protocolVersion':'2024-11-05',
        'capabilities':{},
        'clientInfo':{'name':'test','version':'1.0'}
    }
})
req2 = json.dumps({
    'jsonrpc':'2.0',
    'id':2,
    'method':'tools/call',
    'params':{
        'name':'get_top_news',
        'arguments':{
            'count': 8,
            'lastNDays': 1
        }
    }
})
out, err = p.communicate(req1 + '\n' + req2 + '\n')
print(out)
