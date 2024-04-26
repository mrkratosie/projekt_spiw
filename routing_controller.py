# The program implements a simple controller for a network with 6 hosts and 5 switches.
# The switches are connected in a diamond topology (without vertical links):
#    - 3 hosts are connected to the left (s1) and 3 to the right (s5) edge of the diamond.
# Overall operation of the controller:
#    - default routing is set in all switches on the reception of packet_in messages form the switch,
#    - then the routing for (h1-h4) pair in switch s1 is changed every one second in a round-robin manner to load balance the traffic through switches s3, s4, s2.

from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpidToStr
from pox.lib.addresses import IPAddr, EthAddr
from pox.lib.packet.arp import arp
from pox.lib.packet.ethernet import ethernet, ETHER_BROADCAST
from pox.lib.packet.packet_base import packet_base
from pox.lib.packet.packet_utils import *
import pox.lib.packet as pkt
import json
from pox.lib.recoco import Timer
import time

log = core.getLogger()

s1_dpid = 0
s2_dpid = 0
s3_dpid = 0
s4_dpid = 0
s5_dpid = 0

s1_p1 = 0
s1_p4 = 0
s1_p5 = 0
s1_p6 = 0
s2_p1 = 0
s3_p1 = 0
s4_p1 = 0

pre_s1_p1 = 0
pre_s1_p4 = 0
pre_s1_p5 = 0
pre_s1_p6 = 0
pre_s2_p1 = 0
pre_s3_p1 = 0
pre_s4_p1 = 0

s2_delay = 0
s3_delay = 0
s4_delay = 0



DELAY_THRESHOLD = 250
turn = 0


def getTheTime():  # function to create a timestamp
    flock = time.localtime()
    then = "[%s-%s-%s" % (str(flock.tm_year), str(flock.tm_mon), str(flock.tm_mday))

    if int(flock.tm_hour) < 10:
        hrs = "0%s" % (str(flock.tm_hour))
    else:
        hrs = str(flock.tm_hour)
    if int(flock.tm_min) < 10:
        mins = "0%s" % (str(flock.tm_min))
    else:
        mins = str(flock.tm_min)

    if int(flock.tm_sec) < 10:
        secs = "0%s" % (str(flock.tm_sec))
    else:
        secs = str(flock.tm_sec)

    then += "]%s.%s.%s" % (hrs, mins, secs)
    return then


class myproto(packet_base):
    def __init__(self):
        packet_base.__init__(self)
        self.timestamp = 0

    def hdr(self, payload):
        return struct.pack('!I',
                           self.timestamp)

#wczytywanie intentow
def load_intent():
    global max_delay, src_host, dst_host
    with open('intent.json','r') as f:
        d = json.load(f)
    max_delay = d["delay"]
    src_host = d["src_host"]
    dst_host = d["dst_host"]
    print max_delay, src_host, dst_host

def _timer_func():
    global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid, turn
    global s2_sent_time1, s2_sent_time2, s2_OWD1, s2_OWD2, start_time
    global s3_sent_time1, s3_sent_time2, s3_OWD1, s3_OWD2
    global s4_sent_time1, s4_sent_time2, s4_OWD1, s4_OWD2
    global max_delay, src_host, dst_host
    global s2_delay, s3_delay, s4_delay
    global all_exceeded
    global to_who
    core.openflow.getConnection(s1_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
    core.openflow.getConnection(s2_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
    core.openflow.getConnection(s3_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
    core.openflow.getConnection(s4_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
    # print getTheTime(), "sent the port stats request to s1_dpid"

    # below, routing in s1 towards h4 (IP=10.0.0.4) is set according to the value of the variable turn
    # turn controls the round robin operation
    # turn=0/1/2 => route through s2/s3/s4, respectively
#on sie wykonuje tylko kiedy polaczenie z s1 istnieje

    if s1_dpid <> 0 and not core.openflow.getConnection(s1_dpid) is None:
        #tutaj wysylany jest pakiet port_stats_request aby zmierzyc T1
        core.openflow.getConnection(s1_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        s2_sent_time1 = time.time() * 1000 * 10 - start_time
        #formatowanie pakietu aby zoptymalizowac go pod katem wariacji opoznienia, aby zmierzyc T3
        f = myproto()
        e = pkt.ethernet()
        e.src = EthAddr("0:1:0:0:0:2")
        e.dst = EthAddr("0:2:0:0:0:1")
        #set unregistered EtherType in L2 header type field, here assigned to the probe packet type
        e.type = 0x5577
        msg1 = of.ofp_packet_out() #create PACKET_OUT message object
        msg1.actions.append(of.ofp_action_output(port=4)) #set the output port for the packet
        f.timestamp = int(time.time() * 1000 * 10 - start_time) #set the timestamp in the probe packet
        e.payload = f
        msg1.data = e.pack()
        core.openflow.getConnection(s1_dpid).send(msg1)
        print "=====> probe sent to s2: f=", f.timestamp, " after=", int(time.time() * 1000 * 10 - start_time), " [10*ms]"

        core.openflow.getConnection(s1_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        s3_sent_time1 = time.time() * 1000 * 10 - start_time

        f2 = myproto()
        e2 = pkt.ethernet()
        e2.src = EthAddr("0:1:0:0:0:3")
        e2.dst = EthAddr("0:3:0:0:0:1")
        e2.type = 0x5577
        msg2 = of.ofp_packet_out()
        msg2.actions.append(of.ofp_action_output(port=5))
        f2.timestamp = int(time.time() * 1000 * 10 - start_time)
        e2.payload = f2
        msg2.data = e2.pack()
        core.openflow.getConnection(s1_dpid).send(msg2)
        print "=====> probe sent to s3: f=", f2.timestamp, " after=", int(time.time() * 1000 * 10 - start_time), " [10*ms]"

        core.openflow.getConnection(s1_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        s4_sent_time1 = time.time() * 1000 * 10 - start_time

        f3 = myproto()
        e3 = pkt.ethernet()
        e3.src = EthAddr("0:1:0:0:0:4")
        e3.dst = EthAddr("0:4:0:0:0:1")
        e3.type = 0x5577
        msg3 = of.ofp_packet_out()
        msg3.actions.append(of.ofp_action_output(port=6))
        f3.timestamp = int(time.time() * 1000 * 10 - start_time)
        e3.payload = f3
        msg3.data = e3.pack()
        core.openflow.getConnection(s1_dpid).send(msg3)
        print "=====> probe sent to s4: f=", f3.timestamp, " after=", int(time.time() * 1000 * 10 - start_time), " [10*ms]"

    if s2_dpid <> 0 and not core.openflow.getConnection(s2_dpid) is None:
        # send out port_stats_request packet through switch1 connection dst_dpid (to measure T2)
        core.openflow.getConnection(s2_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        s2_sent_time2 = time.time() * 1000 * 10 - start_time
    if s3_dpid <> 0 and not core.openflow.getConnection(s3_dpid) is None:
        core.openflow.getConnection(s3_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        s3_sent_time2 = time.time() * 1000 * 10 - start_time
    if s4_dpid <> 0 and not core.openflow.getConnection(s4_dpid) is None:
        core.openflow.getConnection(s4_dpid).send(of.ofp_stats_request(body=of.ofp_port_stats_request()))
        s4_sent_time2 = time.time() * 1000 * 10 - start_time
    #ta funkcja sprawdza czy na wszystkich 3 switach delay jest wiekszy niz maxymalny w intent
    #jezeli jest wiekszy to zmienna all_exceeded = 1 jezli we wszystkich nie jest wiekszy to jest ustawiana na 0
    if s3_delay > max_delay and s4_delay > max_delay and s2_delay > max_delay:
        all_exceeded = 1 #yes
    else:
        all_exceeded = 0 #no
    #tutaj jest mechanizm roundrobin, kazdy pakiet obslugiwany jest mechanizmem roundrobin
    #funkcja np. dst_host == "h4"/"h5"/"h6" sprawdza do jakiego hosta ma byc zastosowany intent
    #jezeli np dst_host =="h4", to h5 i h6 dostaja normalnie przekierowanie pakietow echanizmem roundrobin zato
    #h4 jest sprawdzany delay na switchu odpowiadajacemu turn (0/1/2 -> s3/s4/s2) jezeli delay jest wiekszy niz
    #maksymalny to sciezka pakietu nie zostahje zmieniona, natomiast jezeli nie przekracza to jest zmieniania
    if turn == 0:
        if dst_host == "h4":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.5"
            msg.actions.append(of.ofp_action_output(port=5))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.6"
            msg2.actions.append(of.ofp_action_output(port=5))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s3_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.4"
                msg3.actions.append(of.ofp_action_output(port=5))
                core.openflow.getConnection(s1_dpid).send(msg3)

        if dst_host == "h5":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.4"
            msg.actions.append(of.ofp_action_output(port=5))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.6"
            msg2.actions.append(of.ofp_action_output(port=5))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s3_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.5"
                msg3.actions.append(of.ofp_action_output(port=5))
                core.openflow.getConnection(s1_dpid).send(msg3)
        if dst_host == "h6":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.5"
            msg.actions.append(of.ofp_action_output(port=5))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.4"
            msg2.actions.append(of.ofp_action_output(port=5))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s3_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.6"
                msg3.actions.append(of.ofp_action_output(port=5))
                core.openflow.getConnection(s1_dpid).send(msg3)
        turn = 1
        return

    if turn == 1:
        if dst_host == "h4":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.5"
            msg.actions.append(of.ofp_action_output(port=6))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.6"
            msg2.actions.append(of.ofp_action_output(port=6))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s4_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.4"
                msg3.actions.append(of.ofp_action_output(port=6))
                core.openflow.getConnection(s1_dpid).send(msg3)
        if dst_host == "h5":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.4"
            msg.actions.append(of.ofp_action_output(port=6))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.6"
            msg2.actions.append(of.ofp_action_output(port=6))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s4_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.5"
                msg3.actions.append(of.ofp_action_output(port=6))
                core.openflow.getConnection(s1_dpid).send(msg3)
        if dst_host == "h6":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.5"
            msg.actions.append(of.ofp_action_output(port=6))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.4"
            msg2.actions.append(of.ofp_action_output(port=6))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s4_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.6"
                msg3.actions.append(of.ofp_action_output(port=6))
                core.openflow.getConnection(s1_dpid).send(msg3)
        turn = 2
        return

    if turn == 2:
        if dst_host == "h4":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.5"
            msg.actions.append(of.ofp_action_output(port=4))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.6"
            msg2.actions.append(of.ofp_action_output(port=4))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s2_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.4"
                msg3.actions.append(of.ofp_action_output(port=4))
                core.openflow.getConnection(s1_dpid).send(msg3)
        if dst_host == "h5":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.4"
            msg.actions.append(of.ofp_action_output(port=4))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.6"
            msg2.actions.append(of.ofp_action_output(port=4))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s2_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.5"
                msg3.actions.append(of.ofp_action_output(port=4))
                core.openflow.getConnection(s1_dpid).send(msg3)
        if dst_host == "h6":
            msg = of.ofp_flow_mod()
            msg.command = of.OFPFC_MODIFY_STRICT
            msg.priority = 100
            msg.idle_timeout = 0
            msg.hard_timeout = 0
            msg.match.dl_type = 0x0800
            msg.match.nw_dst = "10.0.0.5"
            msg.actions.append(of.ofp_action_output(port=4))
            core.openflow.getConnection(s1_dpid).send(msg)
            msg2 = of.ofp_flow_mod()
            msg2.command = of.OFPFC_MODIFY_STRICT
            msg2.priority = 100
            msg2.idle_timeout = 0
            msg2.hard_timeout = 0
            msg2.match.dl_type = 0x0800
            msg2.match.nw_dst = "10.0.0.4"
            msg2.actions.append(of.ofp_action_output(port=4))
            core.openflow.getConnection(s1_dpid).send(msg2)
            if s2_delay <= max_delay or all_exceeded == 1:
                msg3 = of.ofp_flow_mod()
                msg3.command = of.OFPFC_MODIFY_STRICT
                msg3.priority = 100
                msg3.idle_timeout = 0
                msg3.hard_timeout = 0
                msg3.match.dl_type = 0x0800
                msg3.match.nw_dst = "10.0.0.6"
                msg3.actions.append(of.ofp_action_output(port=4))
                core.openflow.getConnection(s1_dpid).send(msg3)
        turn = 0
        return


def _handle_portstats_received(event):
    # Observe the handling of port statistics provided by this function.

    global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid
    global s1_p1, s1_p4, s1_p5, s1_p6, s2_p1, s3_p1, s4_p1
    global pre_s1_p1, pre_s1_p4, pre_s1_p5, pre_s1_p6, pre_s2_p1, pre_s3_p1, pre_s4_p1
    global s2_sent_time1, s2_sent_time2, s2_OWD1, s2_OWD2, start_time
    global s3_sent_time1, s3_sent_time2, s3_OWD1, s3_OWD2
    global s4_sent_time1, s4_sent_time2, s4_OWD1, s4_OWD2
    global max_delay, src_host, dst_host
    global s2_delay, s3_delay, s4_delay
    received_time = time.time() * 1000 * 10 - start_time
    # measure T1
    if event.connection.dpid == s1_dpid:
        s2_OWD1 = 0.5 * (received_time - s2_sent_time1)
        s3_OWD1 = 0.5 * (received_time - s3_sent_time1)
        s4_OWD1 = 0.5 * (received_time - s4_sent_time1)
        # print "s2_OWD1: ", s2_OWD1, "ms"

    # measure T2
    elif event.connection.dpid == s2_dpid:
        s2_OWD2 = 0.5 * (received_time - s2_sent_time2)
    elif event.connection.dpid == s3_dpid:
        s3_OWD2 = 0.5 * (received_time - s3_sent_time2)
        # print "s2_OWD2: ", s2_OWD2, "ms"
    elif event.connection.dpid == s4_dpid:
        s4_OWD2 = 0.5 * (received_time - s4_sent_time2)
        # print "s2_OWD2: ", s2_OWD2, "ms"

    if event.connection.dpid == s1_dpid:  # The DPID of one of the switches involved in the link


        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s1_p1 = s1_p1
                    s1_p1 = f.rx_packets
                    # print "s1_p1->","TxDrop:", f.tx_dropped,"RxDrop:",f.rx_dropped,"TxErr:",f.tx_errors,"CRC:",f.rx_crc_err,"Coll:",f.collisions,"Tx:",f.tx_packets,"Rx:",f.rx_packets
                if f.port_no == 4:
                    pre_s1_p4 = s1_p4
                    s1_p4 = f.tx_packets
                    s1_p4 = f.tx_bytes
                    # print "s1_p4->","TxDrop:", f.tx_dropped,"RxDrop:",f.rx_dropped,"TxErr:",f.tx_errors,"CRC:",f.rx_crc_err,"Coll:",f.collisions,"Tx:",f.tx_packets,"Rx:",f.rx_packets
                if f.port_no == 5:
                    pre_s1_p5 = s1_p5
                    s1_p5 = f.tx_packets
                if f.port_no == 6:
                    pre_s1_p6 = s1_p6
                    s1_p6 = f.tx_packets

    if event.connection.dpid == s2_dpid:
        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s2_p1 = s2_p1
                    s2_p1 = f.rx_packets
                    # s2_p1=f.rx_bytes
        print getTheTime(), "s1_p4(Sent):", (s1_p4 - pre_s1_p4), "s2_p1(Received):", (s2_p1 - pre_s2_p1)

    if event.connection.dpid == s3_dpid:
        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s3_p1 = s3_p1
                    s3_p1 = f.rx_packets
        print getTheTime(), "s1_p5(Sent):", (s1_p5 - pre_s1_p5), "s3_p1(Received):", (s3_p1 - pre_s3_p1)

    if event.connection.dpid == s4_dpid:
        for f in event.stats:
            if int(f.port_no) < 65534:
                if f.port_no == 1:
                    pre_s4_p1 = s4_p1
                    s4_p1 = f.rx_packets
        print getTheTime(), "s1_p6(Sent):", (s1_p6 - pre_s1_p6), "s4_p1(Received):", (s4_p1 - pre_s4_p1)


def _handle_ConnectionUp(event):
    # waits for connections from all switches, after connecting to all of them it starts a round robin timer for triggering h1-h4 routing changes
    global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid
    global s2_sent_time1, s2_sent_time2, s2_OWD1, s2_OWD2, start_time
    global s3_sent_time1, s3_sent_time2, s3_OWD1, s3_OWD2
    global s4_sent_time1, s4_sent_time2, s4_OWD1, s4_OWD2
    global max_delay, src_host, dst_host
    global s2_delay, s3_delay, s4_delay
    global to_who
    print "ConnectionUp: ", dpidToStr(event.connection.dpid)

    # remember the connection dpid for the switch
    for m in event.connection.features.ports:
        if m.name == "s1-eth1":
            # s1_dpid: the DPID (datapath ID) of switch s1;
            s1_dpid = event.connection.dpid
            print "s1_dpid=", s1_dpid
        elif m.name == "s2-eth1":
            s2_dpid = event.connection.dpid
            print "s2_dpid=", s2_dpid
        elif m.name == "s3-eth1":
            s3_dpid = event.connection.dpid
            print "s3_dpid=", s3_dpid
        elif m.name == "s4-eth1":
            s4_dpid = event.connection.dpid
            print "s4_dpid=", s4_dpid
        elif m.name == "s5-eth1":
            s5_dpid = event.connection.dpid
            print "s5_dpid=", s5_dpid

    # start 1-second recurring loop timer for round-robin routing changes; _timer_func is to be called on timer expiration to change the flow entry in s1
    if s1_dpid <> 0 and s2_dpid <> 0 and s3_dpid <> 0 and s4_dpid <> 0 and s5_dpid <> 0:
        Timer(1, _timer_func, recurring=True)




def _handle_PacketIn(event):
    global s1_dpid, s2_dpid, s3_dpid, s4_dpid, s5_dpid
    global s2_sent_time1, s2_sent_time2, s2_OWD1, s2_OWD2, start_time
    global s3_sent_time1, s3_sent_time2, s3_OWD1, s3_OWD2
    global s4_sent_time1, s4_sent_time2, s4_OWD1, s4_OWD2
    global max_delay, src_host, dst_host
    global s2_delay, s3_delay, s4_delay
    global to_who
    received_time = time.time() * 1000 * 10 - start_time

    packet = event.parsed
    # print "_handle_PacketIn is called, packet.type:", packet.type, " event.connection.dpid:", event.connection.dpid


    if packet.type == 0x5577 and event.connection.dpid == s2_dpid:  # 0x5577 is unregistered EtherType, here assigned to probe packets
        # Process a probe packet received in PACKET_IN message from 'switch1' (dst_dpid), previously sent to 'switch0' (src_dpid) in PACKET_OUT.

        c = packet.find('ethernet').payload
        d, = struct.unpack('!I', c)  # note that d,=... is a struct.unpack and always returns a tuple
        s2_delay = int(received_time - d - s2_OWD1 - s2_OWD2) / 10
        print "s2[ms*10]: received_time=", int(received_time), ", d=", d, ", s2_OWD1=", int(s2_OWD1), ", s2_OWD2=", int(s2_OWD2)
        print "delay:", s2_delay, "[ms] <====="  # divide by 10 to normalise to milliseconds
    if packet.type == 0x5577 and event.connection.dpid == s3_dpid:  # 0x5577 is unregistered EtherType, here assigned to probe packets
        # Process a probe packet received in PACKET_IN message from 'switch1' (dst_dpid), previously sent to 'switch0' (src_dpid) in PACKET_OUT.

        c = packet.find('ethernet').payload
        d, = struct.unpack('!I', c)  # note that d,=... is a struct.unpack and always returns a tuple
        s3_delay = int(received_time - d - s3_OWD1 - s3_OWD2) / 10
        print "s3[ms*10]: received_time=", int(received_time), ", d=", d, ", s3_OWD1=", int(s3_OWD1), ", s3_OWD2=", int(s3_OWD2)
        print "delay:", s3_delay, "[ms] <====="  # divide by 10 to normalise to milliseconds
    if packet.type == 0x5577 and event.connection.dpid == s4_dpid:  # 0x5577 is unregistered EtherType, here assigned to probe packets
        # Process a probe packet received in PACKET_IN message from 'switch1' (dst_dpid), previously sent to 'switch0' (src_dpid) in PACKET_OUT.

        c = packet.find('ethernet').payload
        d, = struct.unpack('!I', c)
        s4_delay = int(received_time - d - s4_OWD1 - s4_OWD2) / 10
        print "s4[ms*10]: received_time=", int(received_time), ", d=", d, ", s4_OWD1=", int(s4_OWD1), ", s4_OWD2=", int(s4_OWD2)
        print "delay:", s4_delay, "[ms] <====="  # divide by 10 to normalise to milliseconds

    # Below, set the default/initial routing rules for all switches and ports.
    # All rules are set up in a given switch on packet_in event received from the switch which means no flow entry has been found in the flow table.
    # This setting up may happen either at the very first pactet being sent or after flow entry expirationn inn the switch

    if event.connection.dpid == s1_dpid:

        a = packet.find(
            'arp')  # If packet object does not encapsulate a packet of the type indicated, find() returns None
        if a and a.protodst == "10.0.0.4":
            msg = of.ofp_packet_out(
                data=event.ofp)  # Create packet_out message; use the incoming packet as the data for the packet out

            msg.actions.append(of.ofp_action_output(port=4))  # Add an action to send to the specified port
            event.connection.send(msg)  # Send message to switch

        if a and a.protodst == "10.0.0.5":
            msg = of.ofp_packet_out(data=event.ofp)

            msg.actions.append(of.ofp_action_output(port=5))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.6":
            msg = of.ofp_packet_out(data=event.ofp)

            msg.actions.append(of.ofp_action_output(port=6))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.1":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=1))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.2":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=2))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.3":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=3))
            event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800  # rule for IP packets (x0800)
        msg.match.nw_dst = "10.0.0.1"
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.2"
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.3"
        msg.actions.append(of.ofp_action_output(port=3))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 1
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.4"
        msg.actions.append(of.ofp_action_output(port=4))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.5"
        msg.actions.append(of.ofp_action_output(port=5))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.6"
        msg.actions.append(of.ofp_action_output(port=6))
        event.connection.send(msg)

    elif event.connection.dpid == s2_dpid:
        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0806  # rule for ARP packets (x0806)
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

    elif event.connection.dpid == s3_dpid:
        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

    elif event.connection.dpid == s4_dpid:
        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 1
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0806
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 2
        msg.match.dl_type = 0x0800
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

    elif event.connection.dpid == s5_dpid:
        a = packet.find('arp')
        if a and a.protodst == "10.0.0.4":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=4))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.5":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=5))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.6":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=6))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.1":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=1))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.2":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=2))
            event.connection.send(msg)

        if a and a.protodst == "10.0.0.3":
            msg = of.ofp_packet_out(data=event.ofp)
            msg.actions.append(of.ofp_action_output(port=3))
            event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.1"
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 10
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.in_port = 6
        msg.actions.append(of.ofp_action_output(port=3))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.1"
        msg.actions.append(of.ofp_action_output(port=1))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.2"
        msg.actions.append(of.ofp_action_output(port=2))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.3"
        msg.actions.append(of.ofp_action_output(port=3))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.4"
        msg.actions.append(of.ofp_action_output(port=4))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.5"
        msg.actions.append(of.ofp_action_output(port=5))
        event.connection.send(msg)

        msg = of.ofp_flow_mod()
        msg.priority = 100
        msg.idle_timeout = 0
        msg.hard_timeout = 0
        msg.match.dl_type = 0x0800
        msg.match.nw_dst = "10.0.0.6"
        msg.actions.append(of.ofp_action_output(port=6))
        event.connection.send(msg)


# As usually, launch() is the function called by POX to initialize the component (routing_controller.py in our case)
# indicated by a parameter provided to pox.py

def launch():
    global s2_sent_time1, s2_sent_time2, s2_OWD1, s2_OWD2, start_time
    global s3_sent_time1, s3_sent_time2, s3_OWD1, s3_OWD2
    global s4_sent_time1, s4_sent_time2, s4_OWD1, s4_OWD2
    global max_delay, src_host, dst_host
    global s2_delay, s3_delay, s4_delay
    global to_who
    start_time = time.time() * 1000 * 10
    # core is an instance of class POXCore (EventMixin) and it can register objects.
    # An object with name xxx can be registered to core instance which makes this object become a "component" available as pox.core.core.xxx.
    # for examples see e.g. https://noxrepo.github.io/pox-doc/html/#the-openflow-nexus-core-openflow
    load_intent()
    core.openflow.addListenerByName("PortStatsReceived",
                                    _handle_portstats_received)  # listen for port stats , https://noxrepo.github.io/pox-doc/html/#statistics-events
    core.openflow.addListenerByName("ConnectionUp",
                                    _handle_ConnectionUp)  # listen for the establishment of a new control channel with a switch, https://noxrepo.github.io/pox-doc/html/#connectionup
    core.openflow.addListenerByName("PacketIn",
                                    _handle_PacketIn)  # listen for the reception of packet_in message from switch, https://noxrepo.github.io/pox-doc/html/#packetin