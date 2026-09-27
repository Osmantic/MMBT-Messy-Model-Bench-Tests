"""CPU-only pinned tokenizer/encoding; no network, API key or GPU authority."""
import hashlib, json, sys, uuid
from pathlib import Path
from tokenizers import Tokenizer
MODEL=Path('/models/DeepSeek-V4.1-Flash')
sys.path.insert(0,str(MODEL/'encoding'))
from encoding import encode_messages
params=json.load(sys.stdin);size=params['inputTokens'];count=params['count']
assert type(size) is int and 512<=size<=65536
assert type(count) is int and 1<=count<=1024
tokenizer=Tokenizer.from_file(str(MODEL/'tokenizer.json'))
def encode(text):return tokenizer.encode(text,add_special_tokens=False).ids
filler=encode('Reference notes: the cache stores recently accessed entries. An implementation should maintain ordering, handle replacement and validate its invariants.\n')
suffix=encode('\nNow write a complete Python LRU cache module with a doubly linked list and dictionary, including get, put, delete, iteration, resize, clear, invariant validation, detailed docstrings and ten usage examples. Return code only. Implement all methods fully.\n<｜Assistant｜></think>')
records=[]
for i in range(count):
    nonce=uuid.uuid4().hex
    prefix=encode(encode_messages([{'role':'user','content':nonce+'\nRead these notes.\n'}],thinking_mode='chat').split('<｜Assistant｜>')[0])
    room=size-len(prefix)-len(suffix);assert room>=0
    ids=prefix+(filler*(room//len(filler)+1))[:room]+suffix;assert len(ids)==size
    digest=hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest()
    records.append({'index':i,'nonce':nonce,'input_ids':ids,'inputTokens':size,'inputIdsSha256':digest})
json.dump({'inputTokens':size,'count':count,'records':records},sys.stdout)
