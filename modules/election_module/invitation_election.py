import threading
import time
import random
from typing import Dict, List, Optional, Callable
from datetime import datetime
from contracts.message_types import ElectionMessage, MessageType
from .node_state import NodeState, ElectionState

class InvitationElection:
    """
    Invitation Election Algorithm
    
    Process:
    1. A node initiates election by becoming CANDIDATE
    2. Candidate sends INVITATION messages to all other nodes
    3. Receivers respond with ACCEPT or REJECT
    4. Accepted nodes join the candidate's group
    5. Node with highest ID in the group becomes LEADER
    6. LEADER broadcasts LEADER message to all nodes
    7. Other nodes become FOLLOWERS
    
    This is different from Bully (which uses priority-based takeover)
    and Ring (which uses a logical ring topology).
    """
    
    def __init__(self, node_id: str, all_node_ids: List[str] = None):
        self.node_id = node_id
        self.all_node_ids: List[str] = all_node_ids or []
        self.election_state = ElectionState(node_id)
        self.running = False
        
        # Message queue for sending election messages
        self.outbox: List[ElectionMessage] = []
        
        # Callbacks
        self.leader_elected_callbacks: List[Callable[[str], None]] = []
        self.state_change_callbacks: List[Callable[[str, str], None]] = []
        self.message_callbacks: List[Callable[[ElectionMessage], None]] = []
        
        # Election timing
        self.election_timeout = 5.0  # seconds to wait for responses
        self.heartbeat_interval = 10.0  # seconds between leader heartbeats
        self.last_leader_heartbeat: datetime = None
        
        # Lock for thread safety
        self.lock = threading.Lock()
    
    def set_all_node_ids(self, node_ids: List[str]):
        """Set the list of all node IDs in the network"""
        self.all_node_ids = node_ids
    
    def add_leader_elected_callback(self, callback: Callable[[str], None]):
        """Add callback for when a leader is elected"""
        self.leader_elected_callbacks.append(callback)
    
    def add_state_change_callback(self, callback: Callable[[str, str], None]):
        """Add callback for state changes (node_id, new_state)"""
        self.state_change_callbacks.append(callback)
    
    def add_message_callback(self, callback: Callable[[ElectionMessage], None]):
        """Add callback for outgoing messages"""
        self.message_callbacks.append(callback)
    
    def _notify_leader_elected(self, leader_id: str):
        """Notify all callbacks about leader election"""
        for callback in self.leader_elected_callbacks:
            try:
                callback(leader_id)
            except Exception as e:
                print(f"Error in leader elected callback: {e}")
    
    def _notify_state_change(self, node_id: str, new_state: str):
        """Notify all callbacks about state change"""
        for callback in self.state_change_callbacks:
            try:
                callback(node_id, new_state)
            except Exception as e:
                print(f"Error in state change callback: {e}")
    
    def _send_message(self, receiver_id: str, message_type: MessageType):
        """Create and queue an election message"""
        msg = ElectionMessage(
            sender_id=self.node_id,
            receiver_id=receiver_id,
            message_type=message_type,
            timestamp=datetime.now()
        )
        self.outbox.append(msg)
        
        # Notify message callbacks
        for callback in self.message_callbacks:
            try:
                callback(msg)
            except Exception as e:
                print(f"Error in message callback: {e}")
    
    def get_outbox_messages(self) -> List[ElectionMessage]:
        """Get all pending outgoing messages and clear the outbox"""
        with self.lock:
            messages = self.outbox.copy()
            self.outbox.clear()
            return messages
    
    def initiate_election(self):
        """Initiate a new election round"""
        with self.lock:
            if self.election_state.is_candidate():
                return  # Already in an election
            
            print(f"[ELECTION] Node {self.node_id} initiating election (term {self.election_state.term + 1})")
            
            # Transition to CANDIDATE
            old_state = self.election_state.state.value
            self.election_state.become_candidate()
            self._notify_state_change(self.node_id, self.election_state.state.value)
            
            # Send INVITATION to all other nodes
            for node_id in self.all_node_ids:
                if node_id != self.node_id:
                    self._send_message(node_id, MessageType.INVITATION)
                    self.election_state.invitations_sent += 1
            
            # Start election timer
            self._start_election_timer()
    
    def _start_election_timer(self):
        """Start a timer to collect responses and decide leadership"""
        def timer_callback():
            time.sleep(self.election_timeout)
            with self.lock:
                if not self.election_state.is_candidate():
                    return
                
                # Election timeout - decide based on responses
                self._decide_leadership()
        
        timer_thread = threading.Thread(target=timer_callback, daemon=True)
        timer_thread.start()
    
    def _decide_leadership(self):
        """Decide leadership after collecting responses"""
        if not self.election_state.is_candidate():
            return
        
        # Check if this node has the highest ID in its group
        group_members = self.election_state.group_members
        highest_id = max(group_members) if group_members else self.node_id
        
        if highest_id == self.node_id:
            # This node becomes LEADER
            self.election_state.become_leader()
            self._notify_state_change(self.node_id, self.election_state.state.value)
            
            # Broadcast LEADER message
            for node_id in self.all_node_ids:
                if node_id != self.node_id:
                    self._send_message(node_id, MessageType.LEADER)
            
            self._notify_leader_elected(self.node_id)
            print(f"[ELECTION] Node {self.node_id} elected as LEADER (term {self.election_state.term})")
        else:
            # Another node in the group has higher ID - wait for their LEADER message
            print(f"[ELECTION] Node {self.node_id} waiting - higher ID node {highest_id} in group")
    
    def receive_message(self, message: ElectionMessage):
        """Process an incoming election message"""
        if message.receiver_id != self.node_id:
            return
        
        with self.lock:
            if message.message_type == MessageType.INVITATION:
                self._handle_invitation(message)
            elif message.message_type == MessageType.ACCEPT:
                self._handle_accept(message)
            elif message.message_type == MessageType.REJECT:
                self._handle_reject(message)
            elif message.message_type == MessageType.LEADER:
                self._handle_leader(message)
    
    def _handle_invitation(self, message: ElectionMessage):
        """Handle an INVITATION message from another node"""
        sender_id = message.sender_id
        
        if self.election_state.is_idle():
            # Accept the invitation and join the group
            self.election_state.become_follower(sender_id)
            self.election_state.group_members = {self.node_id, sender_id}
            self._send_message(sender_id, MessageType.ACCEPT)
            self._notify_state_change(self.node_id, self.election_state.state.value)
            print(f"[ELECTION] Node {self.node_id} accepted invitation from {sender_id}")
            
        elif self.election_state.is_candidate():
            # Two candidates - compare IDs
            if sender_id > self.node_id:
                # Higher ID wins - accept and become follower
                self.election_state.become_follower(sender_id)
                self.election_state.group_members = {self.node_id, sender_id}
                self._send_message(sender_id, MessageType.ACCEPT)
                self._notify_state_change(self.node_id, self.election_state.state.value)
                print(f"[ELECTION] Node {self.node_id} deferred to higher candidate {sender_id}")
            else:
                # This node has higher ID - reject the invitation
                self._send_message(sender_id, MessageType.REJECT)
                self.election_state.invitations_rejected += 1
                print(f"[ELECTION] Node {self.node_id} rejected invitation from {sender_id}")
            
        elif self.election_state.is_follower():
            # Already following someone - reject
            self._send_message(sender_id, MessageType.REJECT)
            print(f"[ELECTION] Node {self.node_id} rejected invitation (already follower)")
            
        elif self.election_state.is_leader():
            # Already a leader - reject
            self._send_message(sender_id, MessageType.REJECT)
            print(f"[ELECTION] Node {self.node_id} rejected invitation (already leader)")
    
    def _handle_accept(self, message: ElectionMessage):
        """Handle an ACCEPT message from another node"""
        sender_id = message.sender_id
        
        if self.election_state.is_candidate():
            self.election_state.add_group_member(sender_id)
            self.election_state.invitations_accepted += 1
            print(f"[ELECTION] Node {self.node_id} received ACCEPT from {sender_id} (group: {self.election_state.group_members})")
            
            # Check if all responses collected
            expected_responses = len(self.all_node_ids) - 1
            total_responses = self.election_state.invitations_accepted + self.election_state.invitations_rejected
            
            if total_responses >= expected_responses:
                self._decide_leadership()
    
    def _handle_reject(self, message: ElectionMessage):
        """Handle a REJECT message from another node"""
        sender_id = message.sender_id
        
        if self.election_state.is_candidate():
            self.election_state.invitations_rejected += 1
            print(f"[ELECTION] Node {self.node_id} received REJECT from {sender_id}")
            
            # Check if all responses collected
            expected_responses = len(self.all_node_ids) - 1
            total_responses = self.election_state.invitations_accepted + self.election_state.invitations_rejected
            
            if total_responses >= expected_responses:
                self._decide_leadership()
    
    def _handle_leader(self, message: ElectionMessage):
        """Handle a LEADER announcement message"""
        leader_id = message.sender_id
        
        # Accept the leader regardless of current state
        if not self.election_state.is_leader():
            old_state = self.election_state.state.value
            self.election_state.become_follower(leader_id)
            self.last_leader_heartbeat = datetime.now()
            self._notify_state_change(self.node_id, self.election_state.state.value)
            self._notify_leader_elected(leader_id)
            print(f"[ELECTION] Node {self.node_id} recognizes {leader_id} as LEADER")
    
    def send_heartbeat(self):
        """Leader sends heartbeat to maintain authority"""
        if self.election_state.is_leader():
            for node_id in self.all_node_ids:
                if node_id != self.node_id:
                    self._send_message(node_id, MessageType.LEADER)
    
    def check_leader_heartbeat(self):
        """Check if leader is still alive based on heartbeat"""
        if self.election_state.is_follower() and self.last_leader_heartbeat:
            elapsed = (datetime.now() - self.last_leader_heartbeat).total_seconds()
            if elapsed > self.heartbeat_interval * 3:
                print(f"[ELECTION] Node {self.node_id} detected leader failure - initiating new election")
                self.election_state.become_idle()
                self.initiate_election()
    
    def get_election_status(self) -> dict:
        """Get current election status"""
        return {
            "node_id": self.node_id,
            "state": self.election_state.state.value,
            "leader_id": self.election_state.leader_id,
            "group_members": list(self.election_state.group_members),
            "term": self.election_state.term,
            "invitations_sent": self.election_state.invitations_sent,
            "invitations_accepted": self.election_state.invitations_accepted,
            "invitations_rejected": self.election_state.invitations_rejected,
            "last_leader_heartbeat": self.last_leader_heartbeat.isoformat() if self.last_leader_heartbeat else None
        }
