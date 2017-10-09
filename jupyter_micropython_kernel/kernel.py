from ipykernel.kernelbase import Kernel
import logging, sys, time, os, re
import serial, socket, serial.tools.list_ports, select
from . import deviceconnector

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

serialtimeout = 0.5
serialtimeoutcount = 10

# use of argparse for handling the %commands in the cells
import argparse, shlex

ap_serialconnect = argparse.ArgumentParser(prog="%serialconnect", add_help=False)
ap_serialconnect.add_argument('--raw', help='Just open connection', action='store_true')
ap_serialconnect.add_argument('portname', type=str, default=0, nargs="?")
ap_serialconnect.add_argument('baudrate', type=int, default=115200, nargs="?")

ap_socketconnect = argparse.ArgumentParser(prog="%socketconnect", add_help=False)
ap_socketconnect.add_argument('--raw', help='Just open connection', action='store_true')
ap_socketconnect.add_argument('ipnumber', type=str)
ap_socketconnect.add_argument('portnumber', type=int)

ap_websocketconnect = argparse.ArgumentParser(prog="%websocketconnect", add_help=False)
ap_websocketconnect.add_argument('--raw', help='Just open connection', action='store_true')
ap_websocketconnect.add_argument('websocketurl', type=str, default="ws://192.168.4.1:8266", nargs="?")
ap_websocketconnect.add_argument("--password", type=str)

ap_writebytes = argparse.ArgumentParser(prog="%writebytes", add_help=False)
ap_writebytes.add_argument('-b', help='binary', action='store_true')
ap_writebytes.add_argument('stringtosend', type=str)

ap_sendtofile = argparse.ArgumentParser(prog="%sendtofile", description="send a file to the microcontroller's file system", add_help=False)
ap_sendtofile.add_argument('-a', help='append', action='store_true')
ap_sendtofile.add_argument('-b', help='binary', action='store_true')
ap_sendtofile.add_argument('destinationfilename', type=str)
ap_sendtofile.add_argument('--source', help="source file", type=str, default="<<cellcontents>>", nargs="?")

def parseap(ap, percentstringargs1):
    try:
        return ap.parse_known_args(percentstringargs1)[0]
    except SystemExit:  # argparse throws these because it assumes you only want to do the command line
        return None  # should be a default one
        
# 1. 8266 websocket feature into the main system
# 2. Complete the implementation of websockets on ESP32
# 3. Create the streaming of pulse measurements to a simple javascript frontend and listing
# 4. Try implementing ESP32 webrepl over these websockets using exec()
# 5. Include %magic commands for flashing the ESP firmware (defaulting to website if file not listed)
# 6. Finish debugging the IR codes



# * upgrade picoweb to handle jpg and png and js
# * code that serves a websocket to a browser from picoweb

# then make the websocket from the ESP32 as well
# then make one that serves out sensor data just automatically
# and access and read that from javascript
# and get the webserving of webpages (and javascript) also to happen

# %readbytes now looks redundant
# * record incoming bytes (eg when in enterpastemode) that haven't been printed 
#    and print them when there is Ctrl-C

# the socket to ESP32 method could either run exec, or 
# save to a file, import it, then delete the modele from sys.modules[]

# * potentially run commands to commission the ESP
#  esptool.py --port /dev/ttyUSB0 erase_flash
#  esptool.py --port /dev/ttyUSB0 --baud 460800 write_flash --flash_size=detect 0 binaries/esp8266-20170108-v1.8.7.bin --flash_mode dio
#  esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash -z 0x1000 esp32...

# It looks like we can handle the 8266 webrepl in the following way:
# import websocket # note no s, so not the asyncio one
#ws = websocket.create_connection("ws://192.168.4.1:8266/")
#result = ws.recv()
#if result == 'Password: ':
#    ws.send("wpass\r\n")
#print("Received '%s'" % result)
#ws.close()
# and then treat like the serial port

# should also handle shell-scripting other commands, like arpscan for mac address to get to ip-numbers

# compress the websocket down to a single straightforward set of code
# take 1-second of data (100 bytes) and time the release of this string 
# to the web-browser


class MicroPythonKernel(Kernel):
    implementation = 'micropython_kernel'
    implementation_version = "v3"

    banner = "MicroPython Serializer"

    language_info = {'name': 'micropython',
                     'codemirror_mode': 'python',
                     'mimetype': 'text/python',
                     'file_extension': '.py'}

    def __init__(self, **kwargs):
        Kernel.__init__(self, **kwargs)
        self.silent = False
        self.dc = deviceconnector.DeviceConnector(self.sres)
    
    def interpretpercentline(self, percentline, cellcontents):
        percentstringargs = shlex.split(percentline)
        percentcommand = percentstringargs[0]

        if percentcommand == ap_serialconnect.prog:
            apargs = parseap(ap_serialconnect, percentstringargs[1:])
            self.dc.serialconnect(apargs.portname, apargs.baudrate)
            if self.dc.workingserial:
                self.sres("\n ** Serial connected **\n\n", 32)
                self.sres(str(self.dc.workingserial))
                self.sres("\n")
                if not apargs.raw:
                    self.dc.enterpastemode()
            return None

        if percentcommand == ap_socketconnect.prog:
            apargs = parseap(ap_socketconnect, percentstringargs[1:])
            self.dc.socketconnect(apargs.ipnumber, apargs.portnumber)
            if self.dc.workingsocket:
                self.sres("\n ** Socket connected **\n\n", 32)
                self.sres(str(self.dc.workingsocket))
                self.sres("\n")
                #if not apargs.raw:
                #    self.dc.enterpastemode()
            return None

        if percentcommand == ap_websocketconnect.prog:
            apargs = parseap(ap_websocketconnect, percentstringargs[1:])
            self.dc.websocketconnect(apargs.websocketurl)
            if self.dc.workingwebsocket: 
                self.sres("\n ** WebSocket connected **\n\n", 32)
                self.sres(str(self.dc.workingwebsocket))
                self.sres("\n")
                if not apargs.raw:
                    pline = self.dc.workingwebsocket.recv()
                    self.sres(pline)
                    if pline == 'Password: ' and apargs.password is not None:
                        self.dc.workingwebsocket.send(apargs.password)
                        self.dc.workingwebsocket.send("\r\n")
                        res = self.dc.workingserialreadall()
                        self.sres(res)  # '\r\nWebREPL connected\r\n>>> '
                        if not apargs.raw:
                            self.dc.enterpastemode()
            return None
            

        if percentcommand == "%lsmagic":
            self.sres("%disconnect\n    disconnects serial\n\n")
            self.sres("%lsmagic\n    list magic commands\n\n")
            self.sres("%readbytes\n    does serial.read_all()\n\n")
            self.sres("%rebootdevice\n    reboots device\n\n")
            self.sres(re.sub("usage: ", "", ap_sendtofile.format_usage()))
            self.sres("    send cell contents or file from disk to device file\n\n")
            self.sres(re.sub("usage: ", "", ap_serialconnect.format_usage()))
            self.sres("    connects to a device over USB wire\n\n")
            self.sres(re.sub("usage: ", "", ap_socketconnect.format_usage()))
            self.sres("    connects to a socket of a device over wifi\n\n")
            self.sres("%suppressendcode\n    doesn't send x04 or wait to read after sending the cell\n")
            self.sres("  (assists for debugging using %writebytes and %readbytes)\n\n")
            self.sres(re.sub("usage: ", "", ap_websocketconnect.format_usage()))
            self.sres("    connects to the webREPL websocket of an ESP8266 over wifi\n")
            self.sres("    websocketurl defaults to ws://192.168.4.1:8266 but be sure to be connected\n\n")
            self.sres(re.sub("usage: ", "", ap_writebytes.format_usage()))
            self.sres("    does serial.write() of the python quoted string given\n\n")
            return None

        if percentcommand == "%disconnect":
            self.dc.disconnect()
            return None
        
        # remaining commands require a connection
        if not self.dc.serialexists():
            return cellcontents
            
        if percentcommand == ap_writebytes.prog:
            apargs = parseap(ap_writebytes, percentstringargs[1:])
            bytestosend = apargs.stringtosend.encode().decode("unicode_escape").encode()
            self.sres(self.dc.writebytes(bytestosend))
            return None
            
        if percentcommand == "%readbytes":
            l = self.dc.workingserialreadall()
            self.sres(str([l]))
            return None
            
        if percentcommand == "%rebootdevice":
            self.dc.sendrebootmessage()
            self.dc.enterpastemode()
            return None
            
        if percentcommand == "%reboot":
            self.sres("Did you mean %rebootdevice?\n", 31)
            return None

        if percentcommand == "%sendbytes":
            self.sres("Did you mean %writebytes?\n", 31)
            return None
            
        if percentcommand == "%reboot":
            self.sres("Did you mean %rebootdevice?\n", 31)
            return None

        if percentcommand in ("%savetofile", "%savefile", "%sendfile"):
            self.sres("Did you mean to write %sendtofile?\n", 31)
            return None

        if percentcommand == ap_sendtofile.prog:
            apargs = parseap(ap_sendtofile, percentstringargs[1:])
            if apargs:
                if apargs.source == "<<cellcontents>>":
                    filecontents = re.sub("^\s*%sendtofile.*\n(?:[ \r]*\n)?", "", cellcontents)
                else:
                    fname = apargs.source or apargs.destinationfilename
                    filecontents = open(fname, ("rb" if apargs.b else "r")).read()
                self.dc.sendtofile(apargs.destinationfilename, apargs.a, apargs.b, filecontents)
            else:
                self.sres(ap_sendtofile.format_usage())
            return None

        self.sres("Unrecognized percentline {}\n".format([percentline]), 31)
        return cellcontents
        
    def runnormalcell(self, cellcontents, bsuppressendcode):
        cmdlines = cellcontents.splitlines(True)
        r = self.dc.workingserialreadall()
        if r:
            self.sres('[priorstuff] ')
            self.sres(str(r))
            
        for line in cmdlines:
            if line:
                if line[-2:] == '\r\n':
                    line = line[:-2]
                elif line[-1] == '\n':
                    line = line[:-1]
                self.dc.writeline(line)
                r = self.dc.workingserialreadall()
                if r:
                    self.sres('[duringwriting] ')
                    self.sres(str(r))
                    
        if not bsuppressendcode:
            self.dc.writebytes(b'\r\x04')
            self.dc.receivestream(bseekokay=True)
        
    def sendcommand(self, cellcontents):
        bsuppressendcode = False  # can't yet see how to get this signal through
        
        # extract any %-commands we have here at the start (or ending?)
        mpercentline = re.match("\s*(%.*)", cellcontents)
        if mpercentline:
            cellcontents = self.interpretpercentline(mpercentline.group(1), cellcontents)
            if cellcontents is None:
                return
                
        if not self.dc.serialexists():
            self.sres("No serial connected\n", 31)
            self.sres("  %serialconnect to connect\n")
            self.sres("  %lsmagic to list commands")
            return
            
        # run the cell contents as normal
        if cellcontents:
            self.runnormalcell(cellcontents, bsuppressendcode)
            
    # 1=bold, 31=red, 32=green, 34=blue; from http://ascii-table.com/ansi-escape-sequences.php
    def sres(self, output, asciigraphicscode=None, n04count=0, clear_output=False):
        if not self.silent:
            if clear_output:
                self.send_response(self.iopub_socket, 'clear_output', {"wait":True})
            if asciigraphicscode:
                output = "\x1b[{}m{}\x1b[0m".format(asciigraphicscode, output)
            stream_content = {'name': ("stdout" if n04count == 0 else "stderr"), 'text': output }
            self.send_response(self.iopub_socket, 'stream', stream_content)

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}

        interrupted = False
        
        # clear buffer out before executing any commands (except the readbytes one)
        if self.dc.serialexists() and not re.match("%readbytes", code):
            priorbuffer = None
            try:
                priorbuffer = self.dc.workingserialreadall()
            except KeyboardInterrupt:
                interrupted = True
            except OSError as e:
                priorbuffer = []
                self.sres("\n\n***Connecton broken [%s]\n" % str(e.strerror), 31)
                self.sres("You may need to reconnect")
                
            if priorbuffer:
                if type(priorbuffer) == bytes:
                    try:
                        priorbuffer = priorbuffer.decode()
                    except UnicodeDecodeError:
                        priorbuffer = str(priorbuffer)
                
                for pbline in priorbuffer.splitlines():
                    if deviceconnector.wifimessageignore.match(pbline):
                        continue   # filter out boring wifi status messages
                    self.sres('[leftinbuffer] ')
                    self.sres(str([pbline]))
                    self.sres('\n')

        try:
            if not interrupted:
                self.sendcommand(code)
        except KeyboardInterrupt:
            interrupted = True
        except OSError as e:
            self.sres("\n\n***OSError [%s]\n\n" % str(e.strerror))
        #except pexpect.EOF:
        #    self.sres(self.asyncmodule.before + 'Restarting Bash')
        #    self.startasyncmodule()

        if interrupted:
            self.sres("\n\n*** Sending Ctrl-C\n\n")
            if self.dc.serialexists():
                self.dc.writebytes(b'\r\x03')
                interrupted = True
                self.dc.receivestream(bseekokay=False, b5secondtimeout=True)
            return {'status': 'abort', 'execution_count': self.execution_count}

        # everything already gone out with send_response(), but could detect errors (text between the two \x04s
        return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}
                    
