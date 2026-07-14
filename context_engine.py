import os
import re
import json
import uuid
import datetime
import math
from llm import chat, stream

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "context_memory.json")

STOPWORDS = {"a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", "as", "at", 
             "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't", "cannot", "could", 
             "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during", "each", "few", "for", 
             "from", "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", 
             "her", "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", 
             "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", 
             "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", 
             "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", 
             "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there", 
             "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through", "to", "too", 
             "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't", 
             "what", "what's", "when", "when's", "where", "where's", "which", "while", "who", "who's", "whom", "why", "why's", 
             "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", 
             "yourselves"}

def tokenize(text):
    """Lowercases, splits alphanumeric tokens and removes stopwords."""
    words = re.findall(r"\b\w+\b", text.lower())
    return [w for w in words if w not in STOPWORDS]

class ContextEngine:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ContextEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.nodes = []
        self.active_node_id = None
        self.last_interaction_time = datetime.datetime.now()
        self.write_buffer = []
        self.buffered_node_id = None
        self.turn_count = 0
        self.load_memory()
        self._initialized = True

    def load_memory(self):
        """Loads context memory from the JSON file."""
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                if not raw:
                    # File exists but is empty (e.g. interrupted write during hot-reload)
                    self.nodes = []
                    return
                data = json.loads(raw)
                self.nodes = data.get("nodes", [])
            except Exception as e:
                print(f"[Context Engine Error] Failed to load context memory: {e}")
                self.nodes = []
        else:
            self.nodes = []

    def save_memory(self):
        """Saves context memory to the JSON file."""
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump({"nodes": self.nodes}, f, indent=2)
        except Exception as e:
            print(f"[Context Engine Error] Failed to save context memory: {e}")

    def clear_memory(self):
        """Deletes the memory file and resets state."""
        self.nodes = []
        self.active_node_id = None
        self.write_buffer = []
        self.buffered_node_id = None
        self.turn_count = 0
        if os.path.exists(MEMORY_FILE):
            try:
                os.remove(MEMORY_FILE)
            except Exception:
                pass

    # --- TF-IDF Router ---

    def calculate_bm25_score(self, query_tokens, node):
        """Computes a simplified BM25/TF-IDF similarity score for a node."""
        doc_text = " ".join([node["topic"]] + node["keywords"])
        doc_tokens = tokenize(doc_text)
        if not doc_tokens:
            return 0.0
        
        score = 0.0
        for token in query_tokens:
            tf = doc_tokens.count(token)
            if tf > 0:
                df = sum(1 for n in self.nodes if token in tokenize(" ".join([n["topic"]] + n["keywords"])))
                idf = math.log((len(self.nodes) - df + 0.5) / (df + 0.5) + 1.0)
                k1 = 1.5
                b = 0.75
                avg_len = sum(len(tokenize(" ".join([n["topic"]] + n["keywords"]))) for n in self.nodes) / len(self.nodes)
                doc_len = len(doc_tokens)
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1.0 - b + b * (doc_len / avg_len)))
        return score

    def route_query(self, query, last_response=""):
        """Resolves target nodes using Enriched Search Keys (Query + Last Response)."""
        if not self.nodes:
            return []

        enriched_query = f"{query} | {last_response}"
        query_tokens = tokenize(enriched_query)
        if not query_tokens:
            return [self.active_node_id] if self.active_node_id else []

        matched_nodes = []
        for node in self.nodes:
            score = self.calculate_bm25_score(query_tokens, node)
            if score > 0.3:
                matched_nodes.append((score, node["id"]))
        
        matched_nodes.sort(key=lambda x: x[0], reverse=True)
        return [nid for _, nid in matched_nodes]

    # --- Transactional Write-Buffering ---

    def buffer_interaction(self, user_msg, agent_resp):
        """Buffers interaction in-memory and flushes if thresholds are met."""
        self.turn_count += 1
        now = datetime.datetime.now()
        
        idle_elapsed = (now - self.last_interaction_time).total_seconds()
        self.last_interaction_time = now

        if self.active_node_id != self.buffered_node_id:
            self.flush_buffer()
            self.buffered_node_id = self.active_node_id

        self.write_buffer.append(f"User: {user_msg}\nAgent: {agent_resp}")

        if len(self.write_buffer) >= 5 or idle_elapsed > 15.0:
            self.flush_buffer()

        if self.turn_count % 10 == 0:
            self.run_garbage_collector()

    def flush_buffer(self):
        """Flushes the buffered turns into a structured summary for the target node."""
        if not self.write_buffer:
            return

        turns_text = "\n\n".join(self.write_buffer)
        self.write_buffer = []

        if not self.active_node_id:
            self.active_node_id = self.create_new_node(turns_text)
            self.buffered_node_id = self.active_node_id
            return

        node = next((n for n in self.nodes if n["id"] == self.active_node_id), None)
        if not node:
            self.active_node_id = self.create_new_node(turns_text)
            self.buffered_node_id = self.active_node_id
            return

        try:
            update_prompt = f"""You are the memory manager. Update the structured JSON summary of the topic: '{node['topic']}'.
Current Summary JSON:
{json.dumps(node['summary'], indent=2)}

New conversation turns:
{turns_text}

Update the fields. Keep it extremely concise, dense with technical details, configurations, and decisions. Preserve code paths.
Response MUST be valid JSON matching this schema:
{{
  "decisions_made": ["list of strings"],
  "current_state": "string describing active system state",
  "pending_items": ["list of strings"],
  "key_technical_references": ["list of files/APIs"]
}}
"""
            resp = chat([{"role": "user", "content": update_prompt}])
            text, _ = stream(resp)
            
            parsed_summary = self._parse_json_defensive(text)
            if parsed_summary:
                node["summary"] = parsed_summary
                node["last_updated"] = datetime.datetime.now().isoformat()
                self.save_memory()
        except Exception as e:
            print(f"[Context Engine Error] Fail to compress/update node: {e}")

    def create_new_node(self, turns_text):
        """Asks the LLM to title and tag a new conversation topic and creates a node."""
        node_id = str(uuid.uuid4())
        try:
            setup_prompt = f"""Analyze this conversation snippet and extract:
1. A concise, clear topic title.
2. 3 to 5 lowercase keywords representing the core subject.
3. A structured summary of the information.

Conversation:
{turns_text}

Response MUST be valid JSON matching this schema:
{{
  "topic": "string topic title",
  "keywords": ["list of lowercase strings"],
  "summary": {{
    "decisions_made": ["list of strings"],
    "current_state": "string describing active system state",
    "pending_items": ["list of strings"],
    "key_technical_references": ["list of files/APIs"]
  }}
}}
"""
            resp = chat([{"role": "user", "content": setup_prompt}])
            text, _ = stream(resp)
            
            parsed = self._parse_json_defensive(text)
            if parsed and "topic" in parsed and "keywords" in parsed and "summary" in parsed:
                new_node = {
                    "id": node_id,
                    "topic": parsed["topic"],
                    "keywords": [k.lower() for k in parsed["keywords"]],
                    "summary": parsed["summary"],
                    "parent_id": None,
                    "last_updated": datetime.datetime.now().isoformat()
                }
                self.nodes.append(new_node)
                self.save_memory()
                return node_id
        except Exception as e:
            print(f"[Context Engine Error] Failed to create new node: {e}")
        
        fallback_node = {
            "id": node_id,
            "topic": "General Discussion",
            "keywords": ["general"],
            "summary": {"decisions_made": [], "current_state": "Conversation started", "pending_items": [], "key_technical_references": []},
            "parent_id": None,
            "last_updated": datetime.datetime.now().isoformat()
        }
        self.nodes.append(fallback_node)
        self.save_memory()
        return node_id

    # --- Hierarchical Node Retrieval & Context Assembly ---

    def meta_compress_nodes(self, node_ids):
        """Deterministically merges and compresses multiple nodes into a single structured summary."""
        matched_nodes = [n for n in self.nodes if n["id"] in node_ids]
        if not matched_nodes:
            return ""

        if len(matched_nodes) == 1:
            n = matched_nodes[0]
            return (
                f"### Active Context: {n['topic']}\n"
                f"Decisions: {', '.join(n['summary']['decisions_made']) or 'None'}\n"
                f"State: {n['summary']['current_state'] or 'Initial'}\n"
                f"Pending: {', '.join(n['summary']['pending_items']) or 'None'}\n"
                f"References: {', '.join(n['summary']['key_technical_references']) or 'None'}\n"
            )

        topics = [n["topic"] for n in matched_nodes]
        decisions = set()
        pending = set()
        references = set()
        states = []

        for n in matched_nodes:
            decisions.update(n["summary"].get("decisions_made", []) or [])
            pending.update(n["summary"].get("pending_items", []) or [])
            references.update(n["summary"].get("key_technical_references", []) or [])
            states.append(f"[{n['topic']}]: {n['summary'].get('current_state', '')}")

        combined_states = " | ".join(states)

        if len(combined_states) > 400:
            try:
                compress_prompt = f"Merge these multiple system states into a single, unified, extremely concise state description:\n" + "\n".join(states) + "\n\nOutput ONLY the unified state description (max 2 sentences)."
                resp = chat([{"role": "user", "content": compress_prompt}])
                text, _ = stream(resp)
                combined_states = text.strip()
            except Exception:
                pass

        return (
            f"### Active Context: {', '.join(topics)}\n"
            f"Decisions: {', '.join(decisions) or 'None'}\n"
            f"State: {combined_states}\n"
            f"Pending: {', '.join(pending) or 'None'}\n"
            f"References: {', '.join(references) or 'None'}\n"
        )

    def assemble_context(self, raw_messages):
        """Constructs the optimized message list, injecting matched and temporal summaries."""
        self.flush_buffer()

        system_msg = next((m for m in raw_messages if m["role"] == "system"), None)
        non_system_msgs = [m for m in raw_messages if m["role"] != "system"]
        
        # Find the index of the last user message to isolate the current turn
        last_user_idx = -1
        for i in range(len(non_system_msgs) - 1, -1, -1):
            if non_system_msgs[i]["role"] == "user":
                last_user_idx = i
                break
                
        if last_user_idx != -1:
            current_turn = non_system_msgs[last_user_idx:]
            history = non_system_msgs[:last_user_idx]
            # Keep up to 4 historical messages (2 previous turns)
            history_buffer = history[-4:] if len(history) > 4 else history
            working_buffer = history_buffer + current_turn
        else:
            working_buffer = non_system_msgs[-5:] if len(non_system_msgs) > 5 else non_system_msgs

        
        last_user = next((m.get("content") or "" for m in reversed(raw_messages) if m["role"] == "user"), "")
        last_agent = next((m.get("content") or "" for m in reversed(raw_messages) if m["role"] == "assistant"), "")
        
        matched_ids = self.route_query(last_user, last_agent)
        if matched_ids:
            self.active_node_id = matched_ids[0]

        loaded_ids = set()
        active_ids_to_load = []

        def gather_ids(nid):
            if not nid or nid in loaded_ids:
                return
            loaded_ids.add(nid)
            active_ids_to_load.append(nid)
            node = next((n for n in self.nodes if n["id"] == nid), None)
            if node and node.get("parent_id"):
                gather_ids(node["parent_id"])

        for nid in matched_ids:
            gather_ids(nid)

        if self.nodes:
            recent_node = max(self.nodes, key=lambda n: n["last_updated"])
            if recent_node["id"] not in loaded_ids:
                gather_ids(recent_node["id"])

        injected_text = ""
        if active_ids_to_load:
            meta_summary = self.meta_compress_nodes(active_ids_to_load)
            injected_text = "\n=== CURRENT CONTEXT MEMORY ===\n" + meta_summary + "=============================\n"

        assembled_messages = []
        if system_msg:
            new_sys = {"role": "system", "content": system_msg["content"] + injected_text}
            assembled_messages.append(new_sys)
        
        assembled_messages.extend(working_buffer)
        return assembled_messages

    # --- Asynchronous Garbage Collector (De-duplication) ---

    def run_garbage_collector(self):
        """Asynchronously cleans up memory by Jaccard pre-screening and merging nodes."""
        if len(self.nodes) < 2:
            return

        merge_candidates = []
        for i in range(len(self.nodes)):
            for j in range(i + 1, len(self.nodes)):
                n1 = self.nodes[i]
                n2 = self.nodes[j]
                
                set1 = set(n1["keywords"])
                set2 = set(n2["keywords"])
                if not set1 or not set2:
                    continue
                
                jaccard = len(set1.intersection(set2)) / len(set1.union(set2))
                if jaccard > 0.4:
                    merge_candidates.append((n1, n2))
        
        for n1, n2 in merge_candidates:
            try:
                merge_prompt = f"""Analyze these two context memory topics:
Topic A: {n1['topic']} (Keywords: {', '.join(n1['keywords'])})
State A: {n1['summary']['current_state']}

Topic B: {n2['topic']} (Keywords: {', '.join(n2['keywords'])})
State B: {n2['summary']['current_state']}

Do these topics cover the same core task, issue, or discussion? If yes, merge them.
Response MUST be valid JSON:
{{
  "should_merge": true,
  "merged_topic": "Unified Title",
  "merged_keywords": ["list of merged lowercase keywords"],
  "merged_summary": {{
    "decisions_made": ["combined unique decisions"],
    "current_state": "combined system state description",
    "pending_items": ["combined unique items"],
    "key_technical_references": ["combined unique references"]
  }}
}}
If they are distinct and should not be merged, respond with:
{{ "should_merge": false }}
"""
                resp = chat([{"role": "user", "content": merge_prompt}])
                text, _ = stream(resp)
                parsed = self._parse_json_defensive(text)
                
                if parsed and parsed.get("should_merge"):
                    n1["topic"] = parsed["merged_topic"]
                    n1["keywords"] = [k.lower() for k in parsed["merged_keywords"]]
                    n1["summary"] = parsed["merged_summary"]
                    n1["last_updated"] = datetime.datetime.now().isoformat()
                    
                    for n in self.nodes:
                        if n.get("parent_id") == n2["id"]:
                            n["parent_id"] = n1["id"]
                    
                    self.nodes.remove(n2)
                    if self.active_node_id == n2["id"]:
                        self.active_node_id = n1["id"]
                    self.save_memory()
                    print(f"[Garbage Collector] Merged duplicate topic node '{n2['topic']}' into '{n1['topic']}'.")
            except Exception as e:
                print(f"[Context Engine GC Error] Error evaluating merge: {e}")

    # --- Parsing Helper ---

    def _parse_json_defensive(self, text):
        """Extracts and parses JSON string from loose text blocks defensively."""
        text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end+1]
            try:
                return json.loads(json_str)
            except Exception:
                json_str_clean = re.sub(r"//.*", "", json_str)
                try:
                    return json.loads(json_str_clean)
                except Exception:
                    pass
        return None
