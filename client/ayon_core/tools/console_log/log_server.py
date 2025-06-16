"""Simple log server for Ayon Core Console Log.

Based on zeroMQ for communication.

"""
import asyncio
import threading
import zmq
from zmq.asyncio import Context, Poller
from loguru import logger


class LogServer:
    """Log server for Ayon Core Console Log."""

    def __init__(self, port: int = 5555):
        self.port = port
        self.context = Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.bind(f"tcp://*:{self.port}")
        self.socket.subscribe("")  # Subscribe to all messages
        logger.info(f"Log server started on port {self.port}")

    def start(self):
        """Start the log server."""
        logger.info("Starting log server...")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        """Run the log server in a separate thread."""
        asyncio.run(self._serve())

    async def _serve(self):
        """Serve log messages asynchronously."""
        logger.info("Entering log server event loop...")
         # This loop will run indefinitely, listening for log messages
         # and printing them to the console.
        while True:
            _, message = await self.socket.recv_multipart()
            logger.info(f"Received log message: {message.decode('utf8').strip()}")