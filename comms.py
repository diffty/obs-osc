import asyncio

from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient


class CommsManager:
    instance = None

    def __init__(self, local_ip, local_port, remote_ip, remote_port):
        CommsManager.instance = self
        
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port

        self.server = None
        self.client = None

    def create_server(self, dispatcher):
        try:
            self.server._loop.stop()
            self.server._loop.close()
            print("Server found, stopped the event loop")

        except:
            print("No server")

        self.server = AsyncIOOSCUDPServer((self.local_ip, self.local_port), dispatcher, asyncio.get_event_loop())
        self.server.serve()
        return self.server

    def create_client(self):
        try:
            self.client._sock.close()
            print("Client found, stopped the event loop")

        except:
            print("No client")
        
        self.client = SimpleUDPClient(self.remote_ip, self.remote_port)
        return self.client
