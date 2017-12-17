"""
Smart home security websocket server.
"""
import logging
import RPi.GPIO as GPIO
import time
import tornado.escape
import tornado.ioloop
import tornado.options
import tornado.web
import tornado.websocket
import os.path

from threading import Thread
from tornado.options import define, options

# Define the default port to be 8888 if none provided.
define("port", default=8888, help="run on the given port", type=int)

MESSAGE_TYPE_KEY = "MESSAGE_TYPE" # The message type key
DEVICE_OPEN_KEY = "DEVICE_OPEN" # The device open key
DEVICE_ARMED_KEY = "DEVICE_ARMED" # The device armed key
DEVICE_ENABLED_KEY = "DEVICE_ENABLED" # The device enabled key
GPIO_PIN = 12 # The active GPIO pin.

class DeviceSocketHandler(tornado.websocket.WebSocketHandler):
    # Hold onto the set of all the connections from the server.
    waiters = set()

    def check_origin(self, origin):
        # Allow connections from other hosts.
        return True

    def get_compression_options(self):
        # Non-None enables compression with default options.
        return {}

    def open(self):
        # Add the socket handler to waiters when a new connection is opened.
        DeviceSocketHandler.waiters.add(self)

    def on_close(self):
        # Remove the socket handler from the waiters when the connection is closed.
        DeviceSocketHandler.waiters.remove(self)    

    @classmethod
    def send_updates(cls, message):
        """
        Notify all the waiters (active connections) the given message.

        Parameters
        ----------
        cls : cls
            The current class.
        message : str
            The message to be send to all the clients.

        """
        logging.info("sending message to %d waiters", len(cls.waiters)) # Log event
        for waiter in cls.waiters: # Iterate through all the waiters
            try:
                waiter.write_message(message) # write the message to the waiter
            except:
                logging.error("Error sending message", exc_info=True) # Log error if message fails to send.
    
    def on_message(self, message):
        """
        Receieve and handle the message send by client.

        Parameters
        ----------
        cls : cls
            The current class.
        message : str
            The message send by client.

        """
        logging.info("got message %r", message) # Log event
        parsed = tornado.escape.json_decode(message) # Parse and decode the json message
        DeviceRunner.handle_message(parsed) # Handle the parsed message
        DeviceSocketHandler.send_updates(DeviceRunner.device_reply_message()) # Reply all waiters with the updated status

class DeviceRunner(Thread):
    # Initialize the isOpen status to None. Update the value after confirming from the device.
    isOpen = None
    # Initialize the isArmed status to None. Update the value after confirming from the device.
    isArmed = None
    # Initialize the isEnabled status to None. Update the value after confirming from the device.
    isEnabled = None

    def __init__(self):
        """
        Create a thread instance that starts polling the GPIO device.        

        Parameters
        ----------
        self : cls
            The current class.
        """
        Thread.__init__(self) # Initialize this instance as a thread
        self.daemon = True # Set the worker as a daemon
        self.setupGPIO() # Setup the GPIO configuration
        self.start() # Start the thread/daemon

    def setupGPIO(self):
        """
        Setup the GPIO mode and GPIO pin listener.
        """
        GPIO.setmode(GPIO.BOARD) # Initializing GPIO to BOARD mode
        GPIO.setup(GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP) # Initialize the pin to notify on pull_up_down
    
    def run(self):
        """
        Poll the GPIO device input every 0.3 seconds to determine the state changes.        

        Parameters
        ----------
        self : cls
            The current class.
        """
        try:            
            while True: # start the thread loop.
                deviceState = GPIO.input(GPIO_PIN) # Get the input from the GPIO input

                # Check if device is enabled and the device state changed
                if DeviceRunner.isArmed and DeviceRunner.isEnabled and deviceState != DeviceRunner.isOpen:
                    DeviceRunner.isOpen = deviceState # Change the device statue to the new state
                    DeviceSocketHandler.send_updates(DeviceRunner.device_notify_message()) # Reply all waiters with the updated status
                time.sleep(0.3) # sleep for a fraction of a second
            GPIO.cleanup() # Cleanup GPIO
        except KeyboardInterrupt: # For Keyboard Interrupt exit            
            GPIO.cleanup() # Cleanup GPIO
    
    @classmethod
    def device_notify_message(cls):
        """
        Creates the notify message encoded with "utf-8". The notification contains:
        1. The Message type of "NOTIFY"
        2. The Device open status         

        Parameters
        ----------
        cls : cls
            The current class.

        Returns
        -------
        str
            The utf-8 encoded device notification message.

        """
        message = {
            MESSAGE_TYPE_KEY: "NOTIFY",
            DEVICE_OPEN_KEY: cls.isOpen,
        } # Create the notification message hash.
        return str(message).encode('utf-8') # Convert the notification message hash to encoded string.
    
    @classmethod
    def device_reply_message(cls):
        """
        Creates the reply message encoded with "utf-8". The reply contains:
        1. The Message type of "REPLY"
        2. The Device armed status 
        3. The Device enabled status

        Parameters
        ----------
        cls : cls
            The current class.

        Returns
        -------
        str
            The utf-8 encoded device reply message.

        """
        message = {
            MESSAGE_TYPE_KEY: "REPLY",
            DEVICE_ARMED_KEY: cls.isArmed,
            DEVICE_ENABLED_KEY: cls.isEnabled,
        } # Create the reply message hash.
        return str(message).encode('utf-8') # Convert the reply message hash to encoded string.

    @classmethod
    def handle_message(cls, message):
        """
        Handle the recieved message by updating the server statuses:
        1. Device open status will be set to true if open otherwise false.
        2. Device armed status will be set to true if armed otherwise false.
        3. Device enabled status will be set to true if enabled otherwise false.

        Parameters
        ----------
        cls : cls
            The current class.
        message : str
            The recieved message.
        """
        # log the handle message request.
        logging.info("got handle_message %r", message)
        
        if (DEVICE_OPEN_KEY in message): # Check if the device open is part of the message.
            DeviceRunner.isOpen = message[DEVICE_OPEN_KEY] # Set the server open status.        
        if (DEVICE_ARMED_KEY in message): # Check if the device armed is part of the message.
            DeviceRunner.isArmed = message[DEVICE_ARMED_KEY] # Set the server armed status.        
        if (DEVICE_ENABLED_KEY in message): # Check if the device enabled is part of the message.
            DeviceRunner.isEnabled = message[DEVICE_ENABLED_KEY] # Set the server enabled status.        

def main():
    """
    Start the tornado websocket application and the device polling.
    """    
    DeviceRunner() # start the device connection, begins polling    
    tornado.options.parse_command_line() # parse the command line options, if port provided    
    app = tornado.web.Application([ 
        (r"/", DeviceSocketHandler),
    ]) # Create the tornado web application with the device socket handler on root url.    
    app.listen(options.port) # Set the application listening port to the given value or default.    
    tornado.ioloop.IOLoop.current().start() # Start the tornado application IO loop.

if __name__ == "__main__":
    """
    The starting point of the script.
    """
    main()
