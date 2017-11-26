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

define("port", default=8888, help="run on the given port", type=int)

MESSAGE_TYPE_KEY = "MESSAGE_TYPE"
DEVICE_OPEN_KEY = "DEVICE_OPEN"
DEVICE_ARMED_KEY = "DEVICE_ARMED"
DEVICE_ENABLED_KEY = "DEVICE_ENABLED"
GPIO_PIN = 12

class DeviceSocketHandler(tornado.websocket.WebSocketHandler):
    waiters = set()

    def check_origin(self, origin):
        return True

    def get_compression_options(self):
        # Non-None enables compression with default options.
        return {}

    def open(self):
        DeviceSocketHandler.waiters.add(self)

    def on_close(self):
        DeviceSocketHandler.waiters.remove(self)    

    @classmethod
    def send_updates(cls, message):
        logging.info("sending message to %d waiters", len(cls.waiters))
        for waiter in cls.waiters:
            try:
                waiter.write_message(message)
            except:
                logging.error("Error sending message", exc_info=True)     
    
    def on_message(self, message):
        logging.info("got message %r", message)
        parsed = tornado.escape.json_decode(message)
        DeviceRunner.handle_message(parsed)
        DeviceSocketHandler.send_updates(DeviceRunner.device_reply_message())        

class DeviceRunner(Thread):
    isOpen = None
    isArmed = None
    isEnabled = None
    needClean = False

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.setupGPIO()
        self.start()

    def setupGPIO(self):
        # Initializing GPIO
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    def run(self):
        try:            
            while True:
                deviceState = GPIO.input(GPIO_PIN)
                if DeviceRunner.isArmed and DeviceRunner.isEnabled and deviceState != DeviceRunner.isOpen:
                    DeviceRunner.isOpen = deviceState
                    DeviceSocketHandler.send_updates(DeviceRunner.device_notify_message())
                time.sleep(0.3)
            GPIO.cleanup() 
        except KeyboardInterrupt:
            # For Keyboard Interrupt exit
            GPIO.cleanup()            
    
    @classmethod
    def device_notify_message(cls):
        message = {
            MESSAGE_TYPE_KEY: "NOTIFY",
            DEVICE_OPEN_KEY: cls.isOpen,
        }
        return str(message).encode('utf-8')
    
    @classmethod
    def device_reply_message(cls):
        message = {
            MESSAGE_TYPE_KEY: "REPLY",
            DEVICE_ARMED_KEY: cls.isArmed,
            DEVICE_ENABLED_KEY: cls.isEnabled,
        }
        return str(message).encode('utf-8')

    @classmethod
    def handle_message(cls, message):
        logging.info("got handle_message %r", message)
        if (DEVICE_OPEN_KEY in message):
            DeviceRunner.isOpen = message[DEVICE_OPEN_KEY]
        if (DEVICE_ARMED_KEY in message):
            DeviceRunner.isArmed = message[DEVICE_ARMED_KEY]
        if (DEVICE_ENABLED_KEY in message):
            DeviceRunner.isEnabled = message[DEVICE_ENABLED_KEY]

def main():
    DeviceRunner()
    tornado.options.parse_command_line()
    app = tornado.web.Application([
        (r"/", DeviceSocketHandler),
    ])
    app.listen(options.port)
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
