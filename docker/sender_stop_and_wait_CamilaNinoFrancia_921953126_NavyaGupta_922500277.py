import socket
import time
import struct

RECEIVER_IP = 'localhost' 
RECEIVER_Port = 5001
Packet_size = 1024
data_size = Packet_size - 4 #4 bytes for seq num
TIMEOUT = 1 #timout if ACK no received

def send_stop_and_wait():
	sendsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sendsock.bind(('', 0)) #sender assignd to any random prt
	sendsock.settimeout(TIMEOUT) #now sender tineout

	#read ythe mp3 file
	with open ('file.mp3','rb') as f:
		data = f.read() # data is of packet size

		seq_num =0
		offset =0

		start_time = time.time() #timer to know when to activate timeout 
		packet_delay = [] #delayed packets are stored here ?


		while offset < len(data):
			whole = data[offset:offset+data_size] #data size is 1020 bytes
			packet_content = struct.pack('!i', seq_num) + whole # contains the sequnce number + broken data part
			print(f"Sending packet with seq num: {seq_num}, size: {len(whole)} bytes") #printing the seq num and size of the packet being sent
			acked = False #when packet is not achknowledged
			packet_start = time.time() #start time of the packet

			while not acked:
				sendsock.sendto(packet_content, (RECEIVER_IP, RECEIVER_Port)) #sender is sending packet to receiver

				try:
					#sender is waiting to received ACK
					ack_data, _ = sendsock.recvfrom(Packet_size) #sender is receiving ACK from receiver
					ack_seq = struct.unpack('!i', ack_data[:4])[0]#extract seq num from ACK
			


					if ack_seq > seq_num : #if ACK seq num = sent packet seq num
						acked = True #packet acknowledged
						packet_end = time.time() #end time of the packet
						packet_delay.append(packet_end - packet_start) #calculate delay for the packet
					
				
				except socket.timeout: #if timeout occurs
					print("Timeout → retransmitting packet") #printing whenever timeout occurs
					#pass

			seq_num += len(whole) #inc seq num for next packet
			offset += len(whole) #move offset for next packet
	

		#to finish the rasnmission we send an empty packet
		fin_packet = struct.pack('!i', seq_num) #empty packet with seq num
		sendsock.sendto(fin_packet, (RECEIVER_IP, RECEIVER_Port))

		#wait for final ACK
		try:
			sendsock.recvfrom(Packet_size) #wait for final ACK
		except socket.timeout:
			pass
		
		finack_packet = struct.pack('!i', seq_num) + b'==FINACK=='
		sendsock.sendto(finack_packet, (RECEIVER_IP, RECEIVER_Port))
		#print("Sent FINACK")
		end_time = time.time() #transmission end time
		tot_time = end_time - start_time #total transmission time
		throughput = len(data) / tot_time 
		avg_delay = sum(packet_delay) / len(packet_delay) if packet_delay else 0 #average delay per packet if any delay hapnd
		metric = 0.3*throughput / 1000 + 0.7 / avg_delay if avg_delay > 0 else 0 #calculate metric
		print(f"{throughput:.7f},{avg_delay:.7f}, {metric:.7f}") #printing throughput, avg delay and metric	
		sendsock.close() #close the socket

if __name__ == "__main__":
	send_stop_and_wait()	


			 #4 bytes for seq num





