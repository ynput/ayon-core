import os
import sys
sys.path.append(os.path.dirname(__file__))

from base_server import BaseRPCServerManager, BaseRPCServerThread


class RPCServerThread(BaseRPCServerThread):
    def thread_safe_call(self, callable_instance, *args):
        """
        Implementation of a thread safe call in Unreal.
        """
        return callable_instance(*args)


class RPCServer(BaseRPCServerManager):
    def __init__(self, port=None):
        """
        Initialize the blender rpc server, with its name and specific port.
        """
        super(RPCServer, self).__init__()
        self.name = 'RPCServer'
        self.port = int(os.environ.get('RPC_PORT', port))
        self.threaded_server_class = RPCServerThread


if __name__ == '__main__':
    rpc_server = RPCServer()
    rpc_server.start(threaded=False)
