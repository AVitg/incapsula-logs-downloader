import datetime
import socket
from SyslogClient import SyslogClient
from time import time

FACILITY = {
    'kern': 0, 'user': 1, 'mail': 2, 'daemon': 3,
    'auth': 4, 'syslog': 5, 'lpr': 6, 'news': 7,
    'uucp': 8, 'cron': 9, 'authpriv': 10, 'ftp': 11,
    'local0': 16, 'local1': 17, 'local2': 18, 'local3': 19,
    'local4': 20, 'local5': 21, 'local6': 22, 'local7': 23,
}

LEVEL = {
    'emerg': 0, 'alert': 1, 'crit': 2, 'err': 3,
    'warning': 4, 'notice': 5, 'info': 6, 'debug': 7
}

"""

Syslog - For sending TCP Syslog messages via socket class

"""


# Create a raw socket client to send messages to syslog server
class SyslogClientCustom(SyslogClient):
    def __init__(self, host, port, socket_type, logger, log_hostname="imperva.com"):
        SyslogClient.__init__(self, host, port, socket_type, logger)
        self.log_hostname=log_hostname
        self.logger.debug("CUSTOM Syslog enabled. Log Hostname: {}".format(log_hostname))

    ''' 
        found actually a log, where the syslog timestamp was "1 Jan", check of end time revealed its "0"
        hence adding this fix, end time is not allowed to be 0 in ESM, and also does not really make sense, as you might sort by end time
        however the event I found it in, was a DDoS event, where the attack is still ongoing... hence end=0 kindof is true, however not complient to ESM/CEF an
    '''
            
    def get_time_from_message_epoch(self, message, time="end="):
        if message.startswith("CEF"):
            epoch = int(str(message.split(time)[1]).split(" ")[0])
        elif message.startswith("LEEF"):
            epoch = int(str(message.split(time)[1]).split("\t")[0])
        else:
            epoch=int(time())
        return(epoch)
        
    def correct_end_time(self,message):
        starttime = self.get_time_from_message_epoch(message,"start=")
        newtime="end={}".format(starttime)
        self.logger.debug("end time=0 time correcting to newtime: {}".format(newtime))
        return(message.replace("end=0", str(newtime)))
        

    def message_customize(self,msg, logfilename):
        if msg != '':            
            msg = msg.replace("Customer=", "flexString1=") # no Customer field in CEF, better to fs1
            msg = msg.replace("cn1=", "flexString2=")
            msg = msg.replace("deviceExternalId=", "cn1=")
            msg = msg.replace("xff=", "cs99=") # yep, there is no cs>6, but it had to go somewhere, and get labels, suggestions welcome
            msg = msg.replace("cs4=", "cs98=") # moving VID
            msg = msg.replace("cs3=", "cs4=") # CO Support to cs4, to match on-prem imperva logs
            msg = msg.replace("sourceServiceName=", "cs3=") # to match on-prem imperva logs
            msg = msg.replace("cs3Label=CO Support", "cs3Label=ServiceName") # cause of moving things around... names needed changes
            msg = msg.replace("cs4Label=VID", "cs4Label=Cookie Support")
            msg = msg.replace("cs1Label=Cap Support", "cs1Label=Captcha Support") # to make it more clear (cap!= capping)
            msg = msg.replace("siteTag=", "cs97=") ## site tag is not always populated
            msg = msg.replace("siteid=", "flexNumber1=") # siteid --> fN1 to make it CEF compliant
            msg = msg.replace("spt=", "dpt=") # spt!=Server Port --> destPort=dpt
            msg = msg.replace("cpt=", "spt=") # cpt (client port) --> sourcePort=spt
            msg = msg.replace("sip=", "dst=") # sip (server ip) --> dst (address)
            msg = msg.replace("ref=", "requestContext=") # ref -->  requestContext / to make it CEF compliant
            msg = msg.replace("cs6=", "deviceProcessName=")  #to make it CEF compliant
            msg = msg.replace("cs5=", "fname=") # to make it CEF compliant
            msg = msg.replace("qstr=", "cs5=") # to make it CEF compliant
            msg = msg.replace("ver=", "cs96=")  # # yep, there is no cs>6, but it had to go somewhere, and get labels, suggestions welcome
            msg = msg.replace("postbody=", "cs6=") # to make it CEF compliant
            msg += " oldFileName="
            msg += logfilename
            msg += " flexString1Label=Customer"
            msg += " flexString2Label=ResponseCode"
            msg += " cs5Label=requestQuery(qstr) "
            msg += " cs6Label=postbody "
            msg += " cs96Label=TLS(ver) "
            msg += " cn1Label=EventId "
            msg += " cs97Label=siteTag "
            msg += " cs98Label=VID "
            msg += " cs99Label=Xff "
        return msg

    # Send the messages
    def send(self, data, logfilename):
        """
        Send syslog packet to given host and port.
        """
        messages = ""
        sock = socket.socket(socket.AF_INET, self.socket_type)
        priority = "<{}>".format(LEVEL['info'] + FACILITY['daemon'] * 8)
        if self.socket_type == socket.SOCK_STREAM:
            # Loop over the data/messages array and create the relevant object(s) to be sent.
            for message in data:
                if "|Normal|" in message: # only send alerts to syslog, otherwise skip
                    continue
                # to have a constant source hostname, or not
                if self.log_hostname == "imperva.com":
                    hostname = self.get_hostname(message)
                else:
                    hostname = self.log_hostname
                timestamp = self.get_time(message)
                application = "cwaf"                
                customized_message=self.message_customize(message,logfilename)
                msg = "{} {} {} {} {}\n".format(priority, timestamp, hostname, application, customized_message)
                messages += msg
            try:
                sock.connect((self.host, int(self.port)))
                sock.send(bytes(messages, 'utf-8'))
                # Returning true if everything is good, if not log the error and return None.
                return True
            except socket.error as e:
                self.logger.error(e)
                return None
            finally:
                sock.close()
        elif self.socket_type == socket.SOCK_DGRAM:
            for message in data:
                if "|Normal|" in message: # only send alerts to syslog, otherwise skip
                    continue
                # to have a constant source hostname, or not
                if self.log_hostname == "imperva.com":
                    hostname = self.get_hostname(message)
                else:
                    hostname = self.log_hostname
                timestamp = self.get_time(message)
                application = "cwaf"
                customized_message=self.message_customize(message,logfilename)                
                if "end=0" in customized_message:
                    customized_message=self.correct_end_time(customized_message)
                msg = "{} {} {} {} {}\n".format(priority, timestamp, hostname, application, customized_message)
                try:
                    sock.sendto(bytes(msg, 'utf-8'), (self.host, int(self.port)))
                except socket.error as e:
                    self.logger.error(e)
                #    return None
                # finally:
                #     sock.close()
                #     # Returning true if everything is good, if not log the error and return None.
            return True
    
    # Function used to get the inbound timestamp to set the indexed time in epoch
        
    def get_time(self, message):
        tformat="%Y-%m-%dT%H:%M:%S.00Z"
        timestamp = datetime.datetime.now().strftime(tformat)
        try:
            if message.startswith("CEF"):
                epoch = int(str(message.split("end=")[1]).split(" ")[0]) / 1000
                # found actually a log, where the syslog timestamp was "1 Jan", check of end time revealed its "0"
                # hence adding this fix
                if epoch == 0:
                    epoch = int(str(message.split("start=")[1]).split(" ")[0]) / 1000
                timestamp = datetime.datetime.fromtimestamp(int(epoch)).strftime(tformat) or \
                            datetime.datetime.now().strftime(tformat)
            elif message.startswith("LEEF"):
                epoch = int(str(message.split("end=")[1]).split("\t")[0]) / 1000
                # see above
                if epoch == 0:
                    epoch = int(str(message.split("start=")[1]).split("\t")[0]) / 1000
                timestamp = datetime.datetime.fromtimestamp(int(epoch)).strftime(tformat) or \
                            datetime.datetime.now().strftime(tformat)
        except IndexError:
            self.logger.error("Error converting epoch time.")
        return timestamp
    
    # Function used to get the host name from the inbound hostname/service name
    def get_hostname(self, message):
        hostname = "imperva.com"
        try:
            if message.startswith("CEF"):
                hostname = str(message.split("sourceServiceName=")[1]).split(" ")[0] or "imperva.com"
            elif message.startswith("LEEF"):
                hostname = str(message.split("sourceServiceName=")[1]).split("\t")[0] or "imperva.com"
        except IndexError:
            self.logger.error("Error getting hostname.")
        return hostname



