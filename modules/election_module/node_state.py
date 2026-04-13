from enum import Enum

class NodeState(Enum):
    """Possible states for a node in the invitation election algorithm"""
    IDLE = "IDLE"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"
    FOLLOWER = "FOLLOWER"

class ElectionState:
    """Tracks the election state of a single node"""
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.state = NodeState.IDLE
        self.leader_id: str = None
        self.group_members: set = set()
        self.term = 0
        self.invitations_sent = 0
        self.invitations_accepted = 0
        self.invitations_rejected = 0
    
    def reset(self):
        """Reset election state for a new round"""
        self.state = NodeState.IDLE
        self.group_members = set()
        self.invitations_sent = 0
        self.invitations_accepted = 0
        self.invitations_rejected = 0
    
    def become_candidate(self):
        """Transition to CANDIDATE state"""
        self.state = NodeState.CANDIDATE
        self.group_members = {self.node_id}
        self.term += 1
    
    def become_leader(self):
        """Transition to LEADER state"""
        self.state = NodeState.LEADER
        self.leader_id = self.node_id
    
    def become_follower(self, leader_id: str):
        """Transition to FOLLOWER state"""
        self.state = NodeState.FOLLOWER
        self.leader_id = leader_id
    
    def become_idle(self):
        """Transition back to IDLE state"""
        self.state = NodeState.IDLE
        self.leader_id = None
        self.group_members = set()
    
    def is_idle(self) -> bool:
        return self.state == NodeState.IDLE
    
    def is_candidate(self) -> bool:
        return self.state == NodeState.CANDIDATE
    
    def is_leader(self) -> bool:
        return self.state == NodeState.LEADER
    
    def is_follower(self) -> bool:
        return self.state == NodeState.FOLLOWER
    
    def add_group_member(self, member_id: str):
        """Add a node to this node's group"""
        self.group_members.add(member_id)
    
    def remove_group_member(self, member_id: str):
        """Remove a node from this node's group"""
        self.group_members.discard(member_id)
    
    def get_state_summary(self) -> dict:
        """Get a summary of the current election state"""
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "leader_id": self.leader_id,
            "group_members": list(self.group_members),
            "term": self.term,
            "invitations_sent": self.invitations_sent,
            "invitations_accepted": self.invitations_accepted,
            "invitations_rejected": self.invitations_rejected
        }
