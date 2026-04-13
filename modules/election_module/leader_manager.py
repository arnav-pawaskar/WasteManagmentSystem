import threading
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime
from contracts.message_types import ElectionMessage, MessageType
from .invitation_election import InvitationElection
from .node_state import NodeState

class LeaderManager:
    """
    Manages the leader election process across all fog nodes.
    Coordinates election message delivery and tracks the overall
    election state of the system.
    """
    
    def __init__(self):
        self.election_nodes: Dict[str, InvitationElection] = {}
        self.current_leader: str = None
        self.election_history: List[Dict] = []
        self.running = False
        
        # Callbacks
        self.leader_change_callbacks: List[Callable[[str], None]] = []
    
    def add_leader_change_callback(self, callback: Callable[[str], None]):
        """Add callback for when leader changes"""
        self.leader_change_callbacks.append(callback)
    
    def _notify_leader_change(self, leader_id: str):
        """Notify all callbacks about leader change"""
        for callback in self.leader_change_callbacks:
            try:
                callback(leader_id)
            except Exception as e:
                print(f"Error in leader change callback: {e}")
    
    def register_node(self, node_id: str, all_node_ids: List[str]):
        """Register a node for election"""
        election = InvitationElection(node_id, all_node_ids)
        
        # Add callback for leader election
        election.add_leader_elected_callback(self._handle_leader_elected)
        
        self.election_nodes[node_id] = election
    
    def _handle_leader_elected(self, leader_id: str):
        """Handle leader election event from any node"""
        old_leader = self.current_leader
        self.current_leader = leader_id
        
        # Record in history
        self.election_history.append({
            "timestamp": datetime.now().isoformat(),
            "leader_id": leader_id,
            "previous_leader": old_leader,
            "term": self.election_nodes.get(leader_id, 
                   next(iter(self.election_nodes.values()), None)).election_state.term if self.election_nodes else 0
        })
        
        # Notify callbacks
        self._notify_leader_change(leader_id)
        
        print(f"[LEADER MANAGER] Leader elected: {leader_id} (previous: {old_leader})")
    
    def start_election(self, initiator_id: str = None):
        """Start an election, optionally from a specific node"""
        if not self.election_nodes:
            return
        
        if initiator_id and initiator_id in self.election_nodes:
            self.election_nodes[initiator_id].initiate_election()
        else:
            # Pick a random node to initiate
            import random
            node_id = random.choice(list(self.election_nodes.keys()))
            self.election_nodes[node_id].initiate_election()
    
    def deliver_messages(self):
        """Deliver election messages between nodes (simulation)"""
        for node_id, node in self.election_nodes.items():
            messages = node.get_outbox_messages()
            for msg in messages:
                target = self.election_nodes.get(msg.receiver_id)
                if target:
                    target.receive_message(msg)
    
    def simulate_leader_failure(self, leader_id: str = None):
        """Simulate leader failure and trigger re-election"""
        target = leader_id or self.current_leader
        if target and target in self.election_nodes:
            node = self.election_nodes[target]
            print(f"[LEADER MANAGER] Simulating failure of leader {target}")
            node.election_state.become_idle()
            
            # Have another node detect the failure and start election
            for nid, n in self.election_nodes.items():
                if nid != target:
                    n.check_leader_heartbeat()
                    break
    
    def start_heartbeat_service(self):
        """Start the leader heartbeat and failure detection service"""
        if self.running:
            return
        
        self.running = True
        
        def heartbeat_loop():
            while self.running:
                try:
                    # Leader sends heartbeat
                    if self.current_leader and self.current_leader in self.election_nodes:
                        self.election_nodes[self.current_leader].send_heartbeat()
                    
                    # Followers check heartbeat
                    for node_id, node in self.election_nodes.items():
                        if node_id != self.current_leader:
                            node.check_leader_heartbeat()
                    
                    # Deliver messages
                    self.deliver_messages()
                    
                    time.sleep(5)
                except Exception as e:
                    print(f"Error in heartbeat loop: {e}")
                    time.sleep(5)
        
        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        print("[LEADER MANAGER] Heartbeat service started")
    
    def stop_heartbeat_service(self):
        """Stop the heartbeat service"""
        self.running = False
        print("[LEADER MANAGER] Heartbeat service stopped")
    
    def get_election_overview(self) -> dict:
        """Get overview of election state across all nodes"""
        nodes = {}
        for node_id, node in self.election_nodes.items():
            nodes[node_id] = node.get_election_status()
        
        return {
            "current_leader": self.current_leader,
            "total_nodes": len(self.election_nodes),
            "nodes": nodes,
            "election_history": self.election_history[-10:],  # Last 10 events
            "total_elections": len(self.election_history)
        }
