"""
Test that detachFromTarget is called when closing a session.
"""
import json
import logging
import sys
import os

# Add the source directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cdp import target
import pytest
import trio
from trio_websocket import serve_websocket

# Import directly from the main module to avoid generated imports
from trio_cdp import CdpConnection, open_cdp

# Import test utilities
from . import fail_after


HOST = '127.0.0.1'


async def start_server(nursery, handler):
    ''' A helper that starts a WebSocket server and runs ``handler`` for each
    connection. Returns the server URL. '''
    server = await nursery.start(serve_websocket, handler, HOST, 0, None)
    return f'ws://{HOST}:{server.port}/devtools/browser/uuid'


@fail_after(5)
async def test_session_detach_on_exit(nursery):
    """Test that detachFromTarget is called when exiting open_session context."""
    detach_called = False
    
    async def handler(request):
        nonlocal detach_called
        try:
            ws = await request.accept()
            
            # Handle "attachToTarget" command
            command = json.loads(await ws.get_message())
            assert command['method'] == 'Target.attachToTarget'
            assert command['params']['targetId'] == 'target1'
            logging.info('Server received attachToTarget: %r', command)
            response = {
                'id': command['id'],
                'result': {
                    'sessionId': 'session1',
                }
            }
            logging.info('Server sending: %r', response)
            await ws.send_message(json.dumps(response))
            
            # Handle "detachFromTarget" command
            command = json.loads(await ws.get_message())
            assert command['method'] == 'Target.detachFromTarget'
            assert command['params']['sessionId'] == 'session1'
            detach_called = True
            logging.info('Server received detachFromTarget: %r', command)
            response = {
                'id': command['id'],
                'result': {}
            }
            logging.info('Server sending: %r', response)
            await ws.send_message(json.dumps(response))
        except Exception:
            logging.exception('Server exception')
    
    server = await start_server(nursery, handler)
    
    async with open_cdp(server) as conn:
        async with conn.open_session(target.TargetID('target1')) as session:
            assert session.session_id == 'session1'
            # Don't do anything else in the session
    
    # After exiting the session context, detach should have been called
    assert detach_called, "detachFromTarget was not called when session closed"


@fail_after(5)
async def test_session_detach_on_exception(nursery):
    """Test that detachFromTarget is called even when an exception occurs in the session."""
    detach_called = False
    
    async def handler(request):
        nonlocal detach_called
        try:
            ws = await request.accept()
            
            # Handle "attachToTarget" command
            command = json.loads(await ws.get_message())
            assert command['method'] == 'Target.attachToTarget'
            logging.info('Server received attachToTarget: %r', command)
            response = {
                'id': command['id'],
                'result': {
                    'sessionId': 'session1',
                }
            }
            await ws.send_message(json.dumps(response))
            
            # Handle "detachFromTarget" command
            command = json.loads(await ws.get_message())
            assert command['method'] == 'Target.detachFromTarget'
            assert command['params']['sessionId'] == 'session1'
            detach_called = True
            logging.info('Server received detachFromTarget: %r', command)
            response = {
                'id': command['id'],
                'result': {}
            }
            await ws.send_message(json.dumps(response))
        except Exception:
            logging.exception('Server exception')
    
    server = await start_server(nursery, handler)
    
    async with open_cdp(server) as conn:
        with pytest.raises(RuntimeError):
            async with conn.open_session(target.TargetID('target1')) as session:
                assert session.session_id == 'session1'
                # Raise an exception in the session
                raise RuntimeError("Test exception")
    
    # After exiting the session context, detach should still have been called
    assert detach_called, "detachFromTarget was not called when session closed with exception"
