__author__ = 'apple'


import sys, os, time, atexit, logging, signal
from signal import SIGTERM
from zk_handler import ZKN9K
import ConfigParser as CP


class Daemon:
    def __init__(self, pidfile, stderr='./log/zk_daemon_err.log', stdout='./log/zk_daemon_out.log', stdin='/dev/null'):
        '''
        Define stdin to /dev/null, stdout and stderr to log files
        pidfile is to record the daemon id for stop method
        '''
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def _daemonize(self):
        '''
        Fork twice to launch a daemon with current working path and umask 0
        In the daemon, dup sys.stdin/out/err to pre-defined stdin/out/err log file.
        Register the exit proc: delpid
        Write daemon pid in pid file
        '''
        #detach from parent1
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        #detach the terminal, and create new session with self as leader
        os.setsid()
        #grant file access authority
        os.umask(0)

        #secondary detachment, from parent2, forbid proc to reopen terminal
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)

        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        #redirect stdin, stdout, stderr to log files
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        #regist the func when proc exist, clean up pid file
        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile,'w+').write("%s\n" % pid)

    def delpid(self):
        '''
        Clean up pidfile
        '''
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon by invoking _daemonize() and _run() in turn.
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)

        # Start the daemon
        self._daemonize()
        self._run()

    def force_stop(self):
        '''
        Check if daemon is there by reading pid file. If no pid, return.
        Simply kill the daemon process.
        '''
        # Get the pid from the pidfile
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return # not an error in a restart
        # Try killing the daemon process
        try:
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)

    def restart(self):
        self.force_stop()
        self.start()

    def _run(self):
        pass

class ZKDaemon(Daemon):
    def __init__(self, pidfile):
        Daemon.__init__(self,pidfile)
        task_mgr_log = './log/' + time.strftime('%Y%m%d') + '.log'
        self.logger = logging.getLogger('N9K_zk_logger')
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter("[%(levelname)s][%(funcName)s][%(asctime)s]%(message)s")
        fh = logging.FileHandler(task_mgr_log)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        config = CP.ConfigParser()
        with open('zk_daemon.conf','r') as cfgfile:
            config.readfp(cfgfile)
        self.zkn9k = ZKN9K(hosts=config.get('zk_hosts','all'),
                           switch_id=int(config.get('switch','id')))

    def stop(self):
        '''
        Send in SIGUSR1 to running daemon in order to clean up zk connection with server.
        Daemon just completes the lifetime all by itself.
        When it exists, delid will be invoked since it is regishttp://bbs.chinaunix.net/viewthread.php?tid=989499tered.
        '''
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return # Cant find daemon pid when SIGTERM received

        # Send SIGUSR1 to daemon and trigger _onsignal_usr1
        os.kill(pid, signal.SIGUSR1)

    def restart(self):
        '''
        Just use parent class's force_stop to kill the daemon, doesn't take care of the zk connection.
        '''
        self.logger.info('Restart will force_stop daemon by killing it')
        Daemon.restart(self)

    def _onsignal_usr1(self,signum,frame):
        '''
        Clean up the zk connection when user stops the daemon by setting a stop sign.
        2 params are must and sent by signal.signal(), signal number and stack frame
        '''
        #Stop the zk connection if it exists
        print('Get signal to disconnect ZK client from server')
        self.zkn9k.stopzk = True

    def _run(self):
        '''
        Rewrite _run method of Daemon
        Register event function here, invoked by decorator defined in zk_handler.
        Exit as long as the stop sign is set to True.
        '''
        # Register the method when SIGUSR1 arrived
        signal.signal(signal.SIGUSR1, self._onsignal_usr1)

        self.zkn9k.reg_read(node='/N9K/ping')
        self.zkn9k.reg_ping(node='/N9K/ping')
        self.zkn9k.reg_int(node='/N9K/e12')
        self.zkn9k.reg_route(node='/N9K/route')
        self.zkn9k.reg_cmd(node='/N9K/bak')
        self.zkn9k.reg_update(node='/N9K/rst')
        self.logger.info("Start ZK Daemon")
        self.zkn9k.zk.start()
        while not self.zkn9k.stopzk:
            pass

        print("Stop ZK at %s" %time.strftime("%Y-%m-%d-%H-%M-%S",time.localtime(time.time())))
        self.logger.info("Stop ZK Daemon")

if __name__ == "__main__":
    if not os.path.exists('./log'):
        os.mkdir('./log')
    daemon = ZKDaemon('./zk_daemon.pid')
    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            print 'start daemon'
            daemon.start()
        elif 'stop' == sys.argv[1]:
            print 'stop daemon'
            daemon.stop()
        elif 'restart' == sys.argv[1]:
            print 'restart daemon'
            daemon.restart()
        elif 'force_stop' == sys.argv[1]:
            print 'force_stopp daemon'
        else:
            print "Unknown command"
            sys.exit(2)
        sys.exit(0)
    else:
        print "usage: %s start|stop|restart|force_stop" % sys.argv[0]
        sys.exit(2)
