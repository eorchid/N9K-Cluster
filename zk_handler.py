#!/usr/bin/python

from kazoo.client import KazooClient
import logging,commands,os,time,sys,pexpect


class ZKN9K:
    def __init__(self, hosts='127.0.0.1:4180', switch_id=1):
        self.zk_hosts = hosts
        self.path = os.getcwd()
        self.switch_id = switch_id
        self.called = False
        self.ping_times = 0
        self.conf_times = 0
        self.read_times = 0
        self.printed = False
        self.data = None
        self.stopzk = False

        logging.basicConfig(
        #    level=logging.DEBUG,
            format="[%(asctime)s] %(name)s:%(levelname)s: %(message)s"
        )

        self.zk = KazooClient(hosts=self.zk_hosts)

    def reg_ping(self,node='/N9K/ping',os='NXOS'):
        @self.zk.DataWatch(node)
        def ping_host(data, stat):
            des_host = data
            if os == 'Linux':
                cmd = 'ping -c2 %s' %des_host
            else:
                cmd = 'vsh -c "ping %s cou 2"' %des_host
            status,output = commands.getstatusoutput(cmd)
            self.ping_times+= 1
            #print(output)
            if self.zk.exists(node+'/switch'+str(self.switch_id)):
                self.zk.set(node+'/switch'+str(self.switch_id), output)
            else:
                self.zk.create(node+'/switch'+str(self.switch_id), output)

    def reg_int(self,node='/N9K/e12'):
        @self.zk.DataWatch(node)
        def interface(data, stat):
            network = data
            #Build configuration file for int e1/2
            if not os.path.exists(self.path + '/conf'):
                os.mkdir(self.path + '/conf')

            int_file = open(self.path + '/conf/e12.cfg','w')
            conf = ['int e1/2\n', 'no sh\n', 'ip add %s%d/24\n' %(network, self.switch_id)]
            int_file.writelines(conf)
            int_file.close()

            if self.conf_times > 0:
                status,output = commands.getstatusoutput('vsh -r %s/conf/e12.cfg' %self.path)

            self.conf_times+= 1

    def reg_read(self, node):
        @self.zk.DataWatch(node)
        def test_func(data, stat):
            self.read_times+= 1
            print('Data in node %s is %s, read %d times' %(node, data, self.read_times))

    def reg_route(self, node):
        path = node + '/switch' + str(self.switch_id)

        @self.zk.DataWatch(path)
        def update_route(data, stat):
            if data == 'start':
                status,output = commands.getstatusoutput('vsh -r %s/conf/static.cfg' %self.path)
                next_path = node+'/switch'+str(self.switch_id+1)
                if self.zk.exists(next_path):
                    self.zk.set(next_path, 'start')

    def reg_cmd(self,node='/N9K/bak'):
        '''
        If data in node is 'all', backup all configurations.
        Otherwise execute the cmd which data identifies.
        Log all result into ../sw_bak folder with file name 'time'.cfg.
        :param node: /N9K/bak
        :return:
        '''
        @self.zk.DataWatch(node)
        def run_cmd(data, stat):
            cmd = data
            #Build configuration file for int e1/2
            if not os.path.exists(self.path + '/sw_bak'):
                os.mkdir(self.path + '/sw_bak')

            bak_file = '%s/sw_bak/%s.cfg' %(self.path,time.strftime("%Y-%m-%d-%H-%M-%S",time.localtime(time.time())))

            #Backup all configuration or part of it
            if cmd == '' or cmd == None:
                pass
            elif cmd =='all':
                status,output = commands.getstatusoutput('vsh -c "sh run" > %s' %bak_file)
            else:
                status,output = commands.getstatusoutput('vsh -c "%s" > %s' %(cmd,bak_file))

    def reg_update(self, node='/N9K/rst',
                    pidfile='./zk_daemon.pid',
                    local_path='./',
                    remote_path='/home/huamjian/zk_*.py',
                    host='huamjian@10.74.82.92',
                    passwd='cisco123'):
        '''
        Refresh the daemon py files from code server
        Restart the daemon according to zk node command.
        :param node:
        :param pidfile:
        :return:
        '''
        path = node+'/switch'+str(self.switch_id)

        @self.zk.DataWatch(path)
        def daemon_update(data, stat):
            if data == 'Yes':
                logging.warning('Daemon is restarted by ZK user to update the handler v5.')
                # Clean up the ZK server restart tag
                self.zk.set(path,'No')
                # Update daemon py files in N9K
                cmd = 'scp %s:%s %s'%(host,remote_path,local_path)
                child = pexpect.spawn(cmd)
                child.expect('password:')
                child.sendline(passwd)
                child.read()
                # Restart the new daemon after code updated.
                os.remove(pidfile)
                python = sys.executable
                os.execl(python, python, * sys.argv)
            elif data == 'No':
                pass
            else:
                logging.warning('The data under rst node is not set correctly.')

if __name__ == "__main__":
    zkn9k = ZKN9K(hosts='192.168.1.11:41802,192.168.1.11:41803,192.168.1.11:41804', switch_id=1)
    zkn9k.reg_read('/N9K/ping')
    zkn9k.zk.start()
    while True:
        if zkn9k.read_times == 2:
            break
    zkn9k.zk.stop()



