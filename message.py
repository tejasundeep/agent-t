from dataclasses import dataclass,field
@dataclass
class ToolCall:id:str;name:str;args:dict=field(default_factory=dict)
@dataclass
class Message:role:str;content:str="";tool_calls:list[ToolCall]=field(default_factory=list)
