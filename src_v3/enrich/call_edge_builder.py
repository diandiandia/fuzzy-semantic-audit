from typing import List, Dict, Any
from src_v3.core.models import CallEdge, IRNode
from src_v3.providers.semantic.base import SemanticProvider

class CallEdgeBuilder:
    """
    Constructs CallEdge relationships in the IR graph.
    """
    @staticmethod
    def build_call_edge(
        src_node: IRNode, 
        dst_node: IRNode, 
        provider: SemanticProvider
    ) -> CallEdge:
        edge_id = f"call_{src_node.node_id}_{dst_node.node_id}"
        confidence = provider.resolution_confidence()
        res_kind = "exact" if confidence >= 0.7 else "fuzzy"
        
        return CallEdge(
            edge_id=edge_id,
            kind="call",
            src_node_id=src_node.node_id,
            dst_node_id=dst_node.node_id,
            confidence=confidence,
            resolution_kind=res_kind,
            provider_trace=[provider.provider_name]
        )
