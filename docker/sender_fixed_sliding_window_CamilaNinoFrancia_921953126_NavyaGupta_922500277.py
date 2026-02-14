import socket
import time
import os
import statistics

import subprocess

class FixedWindowSender:
    def __init__(self, window_size=100):
        self.window_size = window_size
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('localhost', 5002))  # Bind to any available port but 5001
        self.sock.settimeout(0.5)
        self.receiver_addr = ('localhost', 5001) # port to communicate w receiver
        
        # tracking
        self.base = 0
        self.next_seq = 0
        self.window = {}  # seq_id -> (data, send_time)
        
        # metrics
        self.start_time = None
        self.end_time = None
        self.packet_delays = []

    # Will create packets (4B seg_id + data in receiver format)
    def create_packet(self, seq_id, data):
        seq_bytes = int.to_bytes(seq_id, 4, signed=True, byteorder='big')
        return seq_bytes + data
    
    # send packet and track its timing
    def send_packet(self, seq_id, data):
        packet = self.create_packet(seq_id, data)
        self.sock.sendto(packet, self.receiver_addr)
        self.window[seq_id] = (data, time.time())
        self.next_seq = seq_id + len(data) # to track next byte position

    
    # receive ACKs that are non blocking
    def receive_acks(self):
        try:
            while True:
                ack_packet, _ = self.sock.recvfrom(1024)
                
                # Parse ACK: 4-byte seq_id + message
                ack_seq = int.from_bytes(ack_packet[:4], signed=True, byteorder='big')
                ack_msg = ack_packet[4:].decode()
                
                
                # Check for FIN (end of transmission)
                if ack_msg == 'fin':
                    return 'FIN'
                
                # Calculate delay for acknowledged packets (from first send time to ACK receipt)
                for seq_id in list(self.window.keys()):
                    if seq_id < ack_seq:
                        _, send_time = self.window[seq_id]
                        delay = time.time() - send_time
                        self.packet_delays.append(delay)
                        del self.window[seq_id]
                
                # Sliding window
                self.base = ack_seq
        
        # if out of time pass to next ack
        except socket.timeout:
            pass
        return None
    
    # retransmit timed-out packets
    def check_timeouts(self):
        current_time = time.time()
        for seq_id, (data, send_time) in list(self.window.items()):
            if current_time - send_time > 1.0:
                packet = self.create_packet(seq_id, data)
                self.sock.sendto(packet, self.receiver_addr)

    # sending file
    def send_file(self, filepath):
        with open(filepath, 'rb') as f:
            file_data = f.read() # Read file
        
        file_size = len(file_data)
        
        # chunk splitting (1024-4 = 1020 bytes per packet)
        CHUNK_SIZE = 1020
        chunks = []
        byte_offset = 0
        
        # Create chunks with their byte offsets
        while byte_offset < file_size:
            chunk = file_data[byte_offset:byte_offset + CHUNK_SIZE]
            chunks.append((byte_offset, chunk))
            byte_offset += len(chunk)
        
        total_packets = len(chunks)
        
        # Start timer
        self.start_time = time.time()
        
        # Send all data
        chunk_index = 0
        
        while chunk_index < total_packets:
            # Send packets within window
            while chunk_index < total_packets:
                seq_id, data = chunks[chunk_index]
                
                # Check if within window
                if seq_id >= self.base + (self.window_size * CHUNK_SIZE):
                    break
                
                self.send_packet(seq_id, data)
                chunk_index += 1
            
            # Receive ACKs
            result = self.receive_acks()
            if result == 'FIN':
                break
            
            # Check timeouts
            self.check_timeouts()
        
            
        # Send empty final packet
        self.send_packet(file_size, b'')
        
        # Wait for final ACK and FIN with proper timeout and retransmission
        fin_start = time.time()
        last_retransmit = time.time()
        
        while time.time() - fin_start < 10.0:
            result = self.receive_acks()
            if result == 'FIN':
                break
            
            # Retransmit final packet every second
            if time.time() - last_retransmit > 1.0:
                if file_size in self.window:
                    self.send_packet(file_size, b'')
                    last_retransmit = time.time()
        
        # Send FINACK ( 4B seq_id(0) <nd msg)
        finack = int.to_bytes(0, 4, signed=True, byteorder='big') + b'==FINACK=='
        self.sock.sendto(finack, self.receiver_addr)
        
        # Stop timer
        self.end_time = time.time()
        
        self.sock.close()
    
    # calculates throughput, avg delay, and perfomance metric
    def get_metrics(self):
        
        file_size = os.path.getsize('file.mp3') # size of transited data
        total_time = self.end_time - self.start_time # time taken to send data
        
        throughput = file_size / total_time  # bytes/second
        avg_delay = sum(self.packet_delays) / len(self.packet_delays)  # avg delay in (seconds)
        metric = 0.3 * (throughput / 1000) + 0.7 / avg_delay # evaluate performance
        
        return throughput, avg_delay, metric

# Run 10 times (due to inherent randomness) and then average
if __name__ == "__main__":
    
    #initializing metric arrays
    throughputs = []
    delays = []
    metrics = []
    
    for run in range(10):
        # Stop any existing receiver
        subprocess.run(['docker', 'rm', '-f', 'ecs152a-simulator'], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Start new receiver in background
        subprocess.Popen(
            ['docker', 'run', '--name=ecs152a-simulator',
             '--cap-add=NET_ADMIN', '--rm',
             '-p', '5001:5001/udp',
             '-v', f'{os.getcwd()}/hdd:/hdd',
             'ecs152a/simulator'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Wait for receiver to start
        time.sleep(3)
        
        sender = FixedWindowSender(window_size=100)
        sender.send_file('file.mp3')

        #calculating metrics
        tp, delay, metric = sender.get_metrics()
        throughputs.append(tp)
        delays.append(delay)
        metrics.append(metric)
        
        # Clean up receiver
        subprocess.run(['docker', 'rm', '-f', 'ecs152a-simulator'], 
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        time.sleep(2)  # Wait before next run
    
    # Output averages format
    avg_throughput = sum(throughputs)/10
    avg_delay = sum(delays)/10
    avg_metric = sum(metrics)/10

    std_throughput = statistics.stdev(throughputs)
    std_delay = statistics.stdev(delays)
    std_metric = statistics.stdev(metrics)

    
    print(f"{avg_throughput:.7f},{avg_delay:.7f},{avg_metric:.7f}")

    