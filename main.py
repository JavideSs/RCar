
import time, logging, threading
import RPi.GPIO as GPIO
import cwiid, evdev

#==================================================

# Configuration

DEBUG = True

GPIO.setmode(GPIO.BCM)
PIN_MOTOR_A_HIGH = 23
PIN_MOTOR_A_LOW = 24
PIN_MOTOR_B_HIGH = 6
PIN_MOTOR_B_LOW = 5
PIN_MOTOR_A_SPEED = 12
PIN_MOTOR_B_SPEED = 13

#==================================================

PINS_MOTOR = (
    PIN_MOTOR_A_HIGH,
    PIN_MOTOR_A_LOW,
    PIN_MOTOR_B_HIGH,
    PIN_MOTOR_B_LOW
)

PINS_MOTOR_PWM = (
    PIN_MOTOR_A_SPEED,
    PIN_MOTOR_B_SPEED
)

#==================================================

logging.basicConfig(level=logging.NOTSET, format= "[%(levelname)s] %(message)s")
if not DEBUG:
    logging.disable(logging.DEBUG)

#==================================================

def atomic(fn):
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return fn(self, *args, **kwargs)
    return wrapper

#==================================================

class Car():
    def __init__(self, speed):
        self.speed = speed
        self.lock = threading.Lock()
        self.owner = None
        self.last_time = time.time()

        for pin in PINS_MOTOR + PINS_MOTOR_PWM:
            GPIO.setup(pin, GPIO.OUT)
        self.pwm_a = GPIO.PWM(PIN_MOTOR_A_SPEED, 100)
        self.pwm_b = GPIO.PWM(PIN_MOTOR_B_SPEED, 100)
        self.pwm_a.start(self.speed)
        self.pwm_b.start(self.speed)

    @atomic
    def set_owner(self, controller):
        if self.owner is None:
            self.owner = controller
        return self.owner == controller

    @atomic
    def release_owner(self, controller):
        if self.owner == controller:
            self.owner = None
            self.last_time = time.time()

    def is_hot(self):
        return self.owner is not None or (time.time() - self.last_time) < 20.0

    def incrSpeed(self, value):
        self.speed = max(0, min(100, self.speed + value))

    def setMotor(self, left, right):
        def apply(h, l, pwm, speed):
            speed = max(-100, min(100, speed))

            pwm.ChangeDutyCycle(0)
            if speed > 0:
                GPIO.output(h, 1)
                GPIO.output(l, 0)
            elif speed < 0:
                GPIO.output(h, 0)
                GPIO.output(l, 1)
            else:
                GPIO.output(h, 0)
                GPIO.output(l, 0)

            time.sleep(0.1)
            pwm.ChangeDutyCycle(abs(speed))

        apply(PIN_MOTOR_A_HIGH, PIN_MOTOR_A_LOW, self.pwm_a, left)
        apply(PIN_MOTOR_B_HIGH, PIN_MOTOR_B_LOW, self.pwm_b, right)

    def forward(self):
        self.setMotor(self.speed, self.speed)

    def backward(self):
        self.setMotor(-self.speed, -self.speed)

    def left(self):
        self.setMotor(-self.speed, self.speed)

    def right(self):
        self.setMotor(self.speed, -self.speed)

    def stop(self):
        self.setMotor(0, 0)

    def off(self):
        for pin in PINS_MOTOR:
            GPIO.output(pin, 0)
        self.pwm_a.stop()
        self.pwm_a = None
        self.pwm_b.stop()
        self.pwm_b = None
        GPIO.cleanup()

#==================================================

class Controller():
    def __init__(self, car):
        self.car = car
        self.controller = None

    def find(self):
        pass

    def release(self):
        pass

    def initialized(self):
        if not self.controller:
            return False
        if not self.car.set_owner(self):
            self.alert("Oh no! There is another controller connected.")
            self.release()
            return False
        return True

    def mainloop(self):
        pass

    def alert(self, msg):
        logging.info(msg)
        time.sleep(0.1)

#__________________________________________________

class WiiController(Controller):
    def __init__(self, car):
        super().__init__(car)

    def find(self):
        logging.info("- Press 1 + 2 on your Wiimote to connect!")
        try:
            self.controller = cwiid.Wiimote()
            self.controller.rpt_mode = cwiid.RPT_BTN | cwiid.RPT_ACC
            self.alert("Wiimote connected...")
            return True
        except:
            return False

    def release(self):
        if self.controller:
            self.car.release_owner(self)
            self.alert("Wiimote disconnected...")
            self.controller.close()

    def mainloop(self):
        if not self.initialized():
            return

        logging.info("Press 1 + 2 on your Wiimote to disconnect!")
        logging.info("Press HOME on your Wiimote to help!")

        try:
            while True:
                btns = self.controller.state["buttons"]
                acc = self.controller.state["acc"]

                if btns & cwiid.BTN_1 and btns & cwiid.BTN_2:
                    self.release()
                    break

                elif btns & cwiid.BTN_HOME:
                    self.help()

                elif btns & cwiid.BTN_UP:
                    self.car.left()
                    logging.debug("LEFT")

                elif btns & cwiid.BTN_DOWN:
                    self.car.right()
                    logging.debug("RIGHT")

                elif btns & cwiid.BTN_LEFT:
                    self.car.backward()
                    logging.debug("BACKWARD")

                elif btns & cwiid.BTN_RIGHT:
                    self.car.forward()
                    logging.debug("FORWARD")

                elif btns & cwiid.BTN_B:
                    self.car.stop()
                    logging.debug("STOP")

                elif btns & cwiid.BTN_PLUS:
                    self.car.incrSpeed(+50)
                    logging.debug("+ SPEED to " + str(self.car.speed))

                elif btns & cwiid.BTN_MINUS:
                    self.car.incrSpeed(-50)
                    logging.debug("- SPEED to " + str(self.car.speed))

                elif btns & cwiid.BTN_2:
                    x, y, z = acc

                    CENTER = 128
                    x = x - CENTER
                    y = y - CENTER

                    if abs(x) < 5:
                        x = 0
                    if abs(y) < 5:
                        y = 0

                    MAX_DEVIATION = 25
                    speed = int((x / MAX_DEVIATION) * 100)
                    turn = int((y / MAX_DEVIATION) * 100)

                    left = speed - turn
                    right = speed + turn
                    self.car.setMotor(left, right)
                    logging.debug("Go with (" + str(left) + ", " + str(right) + ")")

                time.sleep(0.1)

        except RuntimeError:
            self.release()

    def help(self):
        logging.info(" == Wiimote Help ==")
        logging.info(" Press B to stop, UP/DOWN/LEFT/RIGHT to move")
        logging.info(" Press 2 to move with accelerometer")
        logging.info(" Press + / - to increase / decrease speed")
        logging.info(" Press 1 + 2 to disconnect, HOME to show this help")
        logging.info(" ==================")

    def alert(self, msg):
        if self.controller:
            self.controller.rumble = 1
        super().alert(msg)
        if self.controller:
            self.controller.rumble = 0

#__________________________________________________

class XboxoneController(Controller):
    def __init__(self, car):
        super().__init__(car)

    def find(self):
        TIMEOUT = 10.0
        last_time = time.time()
        while (time.time() - last_time) < TIMEOUT:
            for dev in [evdev.InputDevice(p) for p in evdev.list_devices()]:
                name = dev.name.lower()
                if "xbox" in name or "x-box" in name:
                    try:
                        dev.grab()
                    except OSError:
                        pass

                    logging.info("Xbox controller present. Press MODE on your controller to connect!")

                    try:
                        while (time.time() - last_time) < TIMEOUT:
                            event = dev.read_one()
                            if event is not None and event.type == evdev.ecodes.EV_KEY and event.value == 1 and event.code == evdev.ecodes.BTN_MODE:
                                self.controller = dev
                                self.alert("Xbox controller connected...")
                                return True
                            time.sleep(0.1)
                    except OSError:
                        pass

                    try:
                        dev.ungrab()
                        dev.close()
                    except OSError:
                        pass

            time.sleep(0.1)

        return False

    def release(self):
        if self.controller:
            self.car.release_owner(self)
            self.alert("Xbox controller disconnected...")
            try:
                self.controller.ungrab()
                self.controller.close()
            except OSError:
                pass

    def mainloop(self):
        if not self.initialized():
            return

        self.alert("Press MODE on your controller to disconnect!")
        self.alert("Press SELECT on your controller to help!")

        try:
            x, y = 0, 0
            last_joystick_update = 0
            JOYSTICK_INTERVAL = 0.1
            last_joystick_value = (0,0)

            for event in self.controller.read_loop():
                if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                    if event.code == evdev.ecodes.BTN_MODE:
                        self.release()
                        break

                    if event.code == evdev.ecodes.BTN_SELECT:
                        self.help()

                    elif event.code == evdev.ecodes.BTN_EAST:
                        self.car.stop()
                        logging.debug("STOP")

                    elif event.code == evdev.ecodes.BTN_TR:
                        self.car.incrSpeed(+50)
                        logging.debug("+ SPEED to " + str(self.car.speed))

                    elif event.code == evdev.ecodes.BTN_TL:
                        self.car.incrSpeed(-50)
                        logging.debug("- SPEED to " + str(self.car.speed))

                elif event.type == evdev.ecodes.EV_ABS:
                    if event.code == evdev.ecodes.ABS_HAT0Y:
                        if event.value == -1:
                            self.car.forward()
                            logging.debug("FORWARD")

                        elif event.value == 1:
                            self.car.backward()
                            logging.debug("BACKWARD")

                    elif event.code == evdev.ecodes.ABS_HAT0X:
                        if event.value == -1:
                            self.car.left()
                            logging.debug("LEFT")

                        elif event.value == 1:
                            self.car.right()
                            logging.debug("RIGHT")

                    elif event.code == evdev.ecodes.ABS_X or event.code == evdev.ecodes.ABS_Y:
                        if event.code == evdev.ecodes.ABS_X:
                            x = event.value
                        elif event.code == evdev.ecodes.ABS_Y:
                            y = -event.value

                        if time.time() - last_joystick_update >= JOYSTICK_INTERVAL:
                            MAX_DEVIATION = 32768
                            turn = int((x / MAX_DEVIATION) * 100)
                            speed = int((y / MAX_DEVIATION) * 100)

                            DEADZONE = 50
                            turn = turn if abs(turn) >= DEADZONE else 0
                            speed = speed if abs(speed) >= DEADZONE else 0

                            left = speed + turn
                            right = speed - turn

                            if (left, right) != last_joystick_value:
                                self.car.setMotor(left, right)
                                logging.debug("Go with (" + str(left) + ", " + str(right) + ")")
                                last_joystick_update = time.time()
                                last_joystick_value = (left, right)

        except OSError:
            self.release()

    def help(self):
        logging.info(" == Xbox Controller Help ==")
        logging.info(" Use LEFT STICK to move like the Wii gyroscope")
        logging.info(" Press EAST (B) to stop")
        logging.info(" Press TR (RB) / TL (LB) to increase / decrease speed")
        logging.info(" Press MODE to disconnect, SELECT to show this help")
        logging.info(" =================")

#==================================================

def run_controller(controller_cls, car):
    ctrl = controller_cls(car)
    while car.is_hot():
        if ctrl.find():
            ctrl.mainloop()
        time.sleep(0.1)

def running(car):
    threads = []
    for ctrl_cls in [WiiController, XboxoneController]:
        t = threading.Thread(target=run_controller, args=(ctrl_cls, car))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

#==================================================

if __name__ == "__main__":
    car = Car(speed=50)
    running(car)
    logging.info("There is not controller, closing...")
    car.off()
