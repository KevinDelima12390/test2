import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)

class WebSocketBridge:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.server = None
        self.clients = set()
        self.message_callback = None # Callback for messages from internal server clients
        self.ibis_message_callback = None # Callback for messages from IBIS WS client

    async def handle_client(self, websocket, path):
        logging.info(f"Client connected from {websocket.remote_address}")
        self.clients.add(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logging.info(f"Received message: {data}")
                    if self.message_callback:
                        self.message_callback(data)
                except json.JSONDecodeError:
                    logging.error(f"Could not decode JSON: {message}")
                except Exception as e:
                    logging.error(f"An error occurred in handle_client: {e}")
        except websockets.exceptions.ConnectionClosed as e:
            logging.info(f"Client disconnected: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred in handle_client: {e}")
        finally:
            self.clients.remove(websocket)

    async def start_server(self):
        logging.info(f"Starting internal WebSocket server on ws://{self.host}:{self.port}")
        self.server = await websockets.serve(self.handle_client, self.host, self.port)

    async def send_to_all(self, message):
        if self.clients:
            await asyncio.wait([client.send(json.dumps(message)) for client in self.clients])

    async def connect_to_ibis_ws(self, url, callback):
        self.ibis_message_callback = callback
        logging.info(f"Connecting to IBIS WebSocket at {url}")
        while True:
            try:
                async with websockets.connect(url) as websocket:
                    logging.info("Connected to IBIS WebSocket.")
                    while True:
                        message = await websocket.recv()
                        try:
                            data = json.loads(message)
                            logging.info(f"Received from IBIS: {data}")
                            if self.ibis_message_callback:
                                self.ibis_message_callback(data)
                        except json.JSONDecodeError:
                            logging.error(f"Could not decode IBIS JSON: {message}")
                        except Exception as e:
                            logging.error(f"Error processing IBIS message: {e}")
            except websockets.exceptions.ConnectionClosedOK:
                logging.info("IBIS WebSocket connection closed gracefully. Reconnecting...")
            except Exception as e:
                logging.error(f"IBIS WebSocket connection error: {e}. Reconnecting in 5 seconds...")
                await asyncio.sleep(5)