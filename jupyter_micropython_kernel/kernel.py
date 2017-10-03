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

ap_writebytes = argparse.ArgumentParser(prog="%writebytes", add_help=False)
ap_writebytes.add_argument('-b', help='binary', action='store_true')
ap_writebytes.add_argument('stringtosend', type=str)

ap_sendtofile = argparse.ArgumentParser(prog="%sendtofile", description="send a file to the microcontroller's file system", add_help=False)
ap_sendtofile.add_argument('-a', help='append', action='store_true')
ap_sendtofile.add_argument('destinationfilename', type=str)

def parseap(ap, percentstringargs1):
    try:
        return ap.parse_known_args(percentstringargs1)[0]
    except SystemExit:  # argparse throws these because it assumes you only want to do the command line
        return None  # should be a default one
        
# * build a serial/socket handling object class
# * sendtofile has -a for append
# * robust starting up when already in paste mode

# then make the websocket from the ESP32 as well
# then make one that serves out sensor data just automatically
# and access and read that from javascript
# and get the webserving of webpages (and javascript) also to happen

# * wifi settings and passwords into a file saved on the ESP

# * find out how sometimes things get printed in green
#    colour change to green is done by the character \x1b
#    don't know how to change back to black or to the yellow colour  (these are the syntax highlighting colours)
#    full code is of the form \x1b[0;30m

# * insert comment reminding you to run "python -m jupyter_micropython_kernel.install"
#    after this pip install

# %readbytes now looks redundant
# * record incoming bytes (eg when in enterpastemode) that haven't been printed 
#    and print them when there is Ctrl-C

# * improve the help in usage argparses




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
        self.workingserial = None  # a serial.Serial or a socket.SocketIO
        
    def workingserialreadall(self):  # usually used to clear the incoming buffer
        return self.dc.workingserialreadall()
        
    def serialconnect(self, portname, baudrate):
        self.dc.serialconnect(portname, baudrate)
        self.workingserial = self.dc.workingserial

    def socketconnect(self, ipnumber, portnumber):
        self.dc.socketconnect(ipnumber, portnumber)
        self.workingserial = self.dc.workingsocket

    def receivestream(self, bseekokay, bwarnokaypriors=True, b5secondtimeout=False):
        self.dc.receivestream(bseekokay, bwarnokaypriors, b5secondtimeout)

    def enterpastemode(self):
        self.dc.enterpastemode()
        

    
    def interpretpercentline(self, percentline, cellcontents):
        percentstringargs = shlex.split(percentline)
        percentcommand = percentstringargs[0]

        if percentcommand == ap_serialconnect.prog:
            apargs = parseap(ap_serialconnect, percentstringargs[1:])
            self.serialconnect(apargs.portname, apargs.baudrate)
            if self.workingserial:
                self.sres("\n ** Serial connected **\n\n")
                self.sres(str(self.workingserial))
                self.sres("\n")
                if not apargs.raw:
                    self.enterpastemode()
            return None

        if percentcommand == ap_socketconnect.prog:
            apargs = parseap(ap_socketconnect, percentstringargs[1:])
            self.socketconnect(apargs.ipnumber, apargs.portnumber)
            if self.workingserial:
                self.sres("\n ** Socket connected **\n\n")
                self.sres(str(self.workingserial))
                self.sres("\n")
                #if not apargs.raw:
                #    self.enterpastemode()
            return None

        if percentcommand == "%lsmagic":
            self.sres(ap_serialconnect.format_usage())
            self.sres("%lsmagic list magic commands\n")
            self.sres("%suppressendcode doesn't send x04 or wait to read after sending the cell\n")
            self.sres("  (assists for debugging using %writebytes and %readbytes)\n")
            self.sres("%writebytes does serial.write() on a string b'binary_stuff' \n")
            self.sres(ap_writebytes.format_usage())
            self.sres("%readbytes does serial.read_all()\n")
            self.sres("%rebootdevice reboots device\n")
            self.sres("%disconnects disconnects serial\n")
            self.sres(ap_sendtofile.format_usage())
            self.sres(ap_socketconnect.format_usage())
            return None

        if percentcommand == "%disconnect":
            self.dc.disconnect()
            self.workingserial = None
            return None
        
        # remaining commands require a connection
        if self.workingserial is None:
            return cellcontents
            
        if percentcommand == ap_writebytes.prog:
            apargs = parseap(ap_writebytes, percentstringargs[1:])
            bytestosend = apargs.stringtosend.encode().decode("unicode_escape").encode()
            nbyteswritten = self.workingserial.write(bytestosend)
            if type(self.workingserial) == serial.Serial:
                self.sres("serial.write {} bytes to {} at baudrate {}".format(nbyteswritten, self.workingserial.port, self.workingserial.baudrate))
            else:
                self.sres("serial.write {} bytes to {}".format(nbyteswritten, str(self.workingserial)))
            return None
            
        if percentcommand == "%readbytes":
            l = self.workingserialreadall()
            self.sres(str([l]))
            return None
            
        if percentcommand == "%rebootdevice":
            self.workingserial.write(b"\x03\r")  # quit any running program
            self.workingserial.write(b"\x02\r")  # exit the paste mode with ctrl-B
            self.workingserial.write(b"\x04\r")  # soft reboot code
            self.enterpastemode()
            return None
            
        if percentcommand == "%reboot":
            self.sres("Did you mean %rebootdevice?\n")
            return None

        if percentcommand == "%reboot":
            self.sres("Did you mean %rebootdevice?\n")
            return None

        if percentcommand in ("%savetofile", "%savefile", "%sendfile"):
            self.sres("Did you mean to write %sendtofile?\n")
            return None

        if percentcommand == ap_sendtofile.prog:
            apargs = parseap(ap_sendtofile, percentstringargs[1:])
            cellcontents = re.sub("^\s*%sendtofile.*\n(?:[ \r]*\n)?", "", cellcontents)
            self.dc.sendtofile(apargs.destinationfilename, apargs.a, cellcontents)
            return None

        return cellcontents
        
    def runnormalcell(self, cellcontents, bsuppressendcode):
        cmdlines = cellcontents.splitlines(True)
        r = self.workingserialreadall()
        if r:
            self.sres('[priorstuff] ')
            self.sres(str(r))
            
        for line in cmdlines:
            if line:
                if line[-2:] == '\r\n':
                    line = line[:-2]
                elif line[-1] == '\n':
                    line = line[:-1]
                self.workingserial.write(line.encode("utf8"))
                self.workingserial.write(b'\r\n')
                r = self.workingserialreadall()
                if r:
                    self.sres('[duringwriting] ')
                    self.sres(str(r))
                    
        if not bsuppressendcode:
            self.workingserial.write(b'\r\x04')
            self.receivestream(bseekokay=True)
        
    def sendcommand(self, cellcontents):
        bsuppressendcode = False  # can't yet see how to get this signal through
        
        # extract any %-commands we have here at the start (or ending?)
        mpercentline = re.match("\s*(%.*)", cellcontents)
        if mpercentline:
            cellcontents = self.interpretpercentline(mpercentline.group(1), cellcontents)
            if cellcontents is None:
                return
                
        if self.workingserial is None:
            self.sres("No serial connected\n")
            self.sres("  %serialconnect to connect\n")
            self.sres("  %lsmagic to list commands")
            return
            
        # run the cell contents as normal
        if cellcontents:
            self.runnormalcell(cellcontents, bsuppressendcode)
            

    def sres(self, output):
        if not self.silent:
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}

        interrupted = False
        if self.workingserial:
            priorbuffer = None
            try:
                priorbuffer = self.workingserialreadall()
            except KeyboardInterrupt:
                interrupted = True
            except OSError as e:
                priorbuffer = []
                self.sres("\n\n***Connecton broken [%s]\n" % str(e.strerror))
                self.sres("You may need to reconnect")
                
            if priorbuffer:
                for pbline in priorbuffer.splitlines():
                    try:
                        ur = pbline.decode()
                    except UnicodeDecodeError:
                        ur = str(pbline)
                    if deviceconnector.wifimessageignore.match(ur):
                        continue   # filter out boring wifi status messages
                    self.sres('[leftinbuffer] ')
                    self.sres(str([ur]))
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
            if self.workingserial:
                self.workingserial.write(b'\r\x03')
                interrupted = True
                self.receivestream(bseekokay=False, b5secondtimeout=True)
            return {'status': 'abort', 'execution_count': self.execution_count}

        # everything already gone out with send_response(), but could detect errors (text between the two \x04s
        return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}
                    
