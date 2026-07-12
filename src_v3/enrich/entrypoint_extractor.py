from typing import List, Dict, Any
from src_v3.core.models import Entrypoint, LanguageShard
from src_v3.providers.framework.base import FrameworkProvider
from src_v3.storage.ir_store import IRStore

class EntrypointExtractor:
    """
    Extracts public API/framework entrypoints and registers them as unified IR Entrypoint nodes.
    """
    @staticmethod
    def extract_and_register(
        workspace_dir: str, 
        shard: LanguageShard, 
        framework_providers: List[FrameworkProvider]
    ) -> None:
        ir_store = IRStore(workspace_dir)
        all_symbols = ir_store.get_symbol_nodes()
        symbols_map = {sn.node_id: sn for sn in all_symbols}
        
        new_nodes = []
        
        for provider in framework_providers:
            try:
                entrypoints = provider.extract_entrypoints(ir_store)
                for ep in entrypoints:
                    node_id = ep["node_id"]
                    if node_id in symbols_map:
                        ep_node_id = f"ep_{node_id}"
                        ep_node = Entrypoint(
                            node_id=ep_node_id,
                            kind="entrypoint",
                            lang=shard.lang,
                            file=symbols_map[node_id].file,
                            symbol=symbols_map[node_id].symbol,
                            span=symbols_map[node_id].span,
                            attributes={
                                "route": ep["route"],
                                "method": ep["method"],
                                "confidence": ep["confidence"],
                                "provider_name": provider.framework_name,
                                "framework_name": provider.framework_name,
                                "framework_trace": ep.get("framework_trace", {})
                            }
                        )
                        new_nodes.append(ep_node)
            except Exception:
                pass
                
        if new_nodes:
            ir_store.save(new_nodes, [], overwrite=False)
