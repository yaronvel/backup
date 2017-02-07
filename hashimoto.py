import pickle
from pycoin.serialize import b2h, h2b
from pycoin import encoding
import rlp
from ethereum import tester, utils, abi, blocks, transactions


import sha3, copy

def get_seedhash(block_number):
     s = '\x00' * 32
     for i in range(block_number // EPOCH_LENGTH):
         s = serialize_hash(sha3_256(s))
     return s
 
# Assumes little endian bit ordering (same as Intel architectures)
def decode_int(s):
    return int(s[::-1].encode('hex'), 16) if s else 0

def encode_int(s):
    a = "%x" % s
    return '' if s == 0 else ('0' * (len(a) % 2) + a).decode('hex')[::-1]

def zpad(s, length):
    return s + '\x00' * max(0, length - len(s))

def serialize_hash(h):
    return ''.join([zpad(encode_int(x), 4) for x in h])

def deserialize_hash(h):
    return [decode_int(h[i:i+WORD_BYTES]) for i in range(0, len(h), WORD_BYTES)]

def hash_words(h, sz, x):
    if isinstance(x, list):
        x = serialize_hash(x)
    y = h(x)
    return deserialize_hash(y)

def serialize_cache(ds):
    return ''.join([serialize_hash(h) for h in ds])

serialize_dataset = serialize_cache

# sha3 hash function, outputs 64 bytes

from Crypto.Hash import keccak
mysha3_512 = lambda x: keccak.new(digest_bits=512, data=x).digest()


def sha3_512(x):
    return hash_words(lambda v: mysha3_512(v), 64, x)

def sha3_256(x):
    return hash_words(lambda v: utils.sha3_256(v), 32, x)

def xor(a, b):
    return a ^ b

def isprime(x):
    for i in range(2, int(x**0.5)):
         if x % i == 0:
             return False
    return True



WORD_BYTES = 4                    # bytes in word
DATASET_BYTES_INIT = 2**30        # bytes in dataset at genesis
DATASET_BYTES_GROWTH = 2**23      # dataset growth per epoch
CACHE_BYTES_INIT = 2**24          # bytes in cache at genesis
CACHE_BYTES_GROWTH = 2**17        # cache growth per epoch
CACHE_MULTIPLIER=1024             # Size of the DAG relative to the cache
EPOCH_LENGTH = 30000              # blocks per epoch
MIX_BYTES = 128                   # width of mix
HASH_BYTES = 64                   # hash length in bytes
DATASET_PARENTS = 256             # number of parents of each dataset element
CACHE_ROUNDS = 3                  # number of rounds in cache production
ACCESSES = 64                     # number of accesses in hashimoto loop


def get_cache_size(block_number):
    sz = CACHE_BYTES_INIT + CACHE_BYTES_GROWTH * (block_number // EPOCH_LENGTH)
    sz -= HASH_BYTES
    while not isprime(sz / HASH_BYTES):
        sz -= 2 * HASH_BYTES
    return sz

def get_full_size(block_number):
    sz = DATASET_BYTES_INIT + DATASET_BYTES_GROWTH * (block_number // EPOCH_LENGTH)
    sz -= MIX_BYTES
    while not isprime(sz / MIX_BYTES):
        sz -= 2 * MIX_BYTES
    return sz


def mkcache(cache_size, seed):
    n = cache_size // HASH_BYTES
    # Sequentially produce the initial dataset
    o = [sha3_512(seed)]
    for i in range(1, n):
        o.append(sha3_512(o[-1]))
    # Use a low-round version of randmemohash
    for _ in range(CACHE_ROUNDS):
        for i in range(n):
            v = o[i][0] % n
            o[i] = sha3_512(map(xor, o[(i-1+n) % n], o[v]))

    return o

FNV_PRIME = 0x01000193

def fnv(v1, v2):
    return (v1 * FNV_PRIME ^ v2) % 2**32


def calc_dataset_item(cache, i):
    n = len(cache)
    r = HASH_BYTES // WORD_BYTES
    # initialize the mix
    mix = copy.copy(cache[i % n])
    mix[0] ^= i
    mix = sha3_512(mix)
    # fnv it with a lot of random cache nodes based on i
    for j in range(DATASET_PARENTS):
        cache_index = fnv(i ^ j, mix[j % r])
        mix = map(fnv, mix, cache[cache_index % n])
    return sha3_512(mix)



elements_input_for_contract = []
def push_data( element ):
    global elements_input_for_contract
    first_int = 0
    second_int = 0
    
    for i in range(8):
        first_int = first_int + element[i] * 2 ** (32*i)
        second_int = second_int + element[i + 8] * 2 ** (32*i)
        
    elements_input_for_contract.append(first_int)
    elements_input_for_contract.append(second_int)

def hashimoto(header, nonce, full_size, dataset_lookup):
    ps = []
    n = full_size / HASH_BYTES
    w = MIX_BYTES // WORD_BYTES
    mixhashes = MIX_BYTES / HASH_BYTES
    # combine header+nonce into a 64 byte seed 
    s = sha3_512(header + nonce[::-1])
    # start the mix with replicated s
    mix = []
    for _ in range(MIX_BYTES / HASH_BYTES):
        mix.extend(s)
    # mix in random dataset nodes
    for i in range(ACCESSES):
        p = fnv(i ^ s[0], mix[i % w]) % (n // mixhashes) * mixhashes
        newdata = []
        for j in range(MIX_BYTES / HASH_BYTES):
            push_data(dataset_lookup(p + j))
            #print str(elements_input_for_contract) 
            #sd
            newdata.extend(dataset_lookup(p + j))
        ps.append(p//2)
            
        mix = map(fnv, mix, newdata)
    # compress mix
    cmix = []
    for i in range(0, len(mix), 4):
        cmix.append(fnv(fnv(fnv(mix[i], mix[i+1]), mix[i+2]), mix[i+3]))

    return {
        "mix digest": serialize_hash(cmix),
        "result": serialize_hash(sha3_256(s+cmix))
    }

def hashimoto_light(full_size, cache, header, nonce):
    return hashimoto(header, nonce, full_size, lambda x: calc_dataset_item(cache, x))

def hashimoto_full(full_size, dataset, header, nonce):
    return hashimoto(header, nonce, full_size, lambda x: dataset[x])



################################################################################

class MerkleNode:        
    def __init__(self, is_leaf, value, left_elem, right_elem):
        if is_leaf:
            self.value = value
            self.leaf = True
        else:
            self.left = left_elem
            self.right = right_elem
            
            self.value = utils.sha3(left_elem.value + right_elem.value)
            self.leaf = False
    def get_branch(self, index, depth): # note that index should be reversed
        if self.leaf:
            return []
        move_right = index & (1 << depth)
        if move_right:
            result += self.right.get_branch(index,depth+1)
            result += [self.left.value]
        else:
            result += self.left.get_branch(index,depth+1)
            result += [self.right.value]
        return result
        

def compute_cache_merkle_tree( full_size, dataset_lookup, level, prev_level_nodes = None ):
    print "level: " + str(level)
    level_nodes = []
    if level == 1:
        return (prev_level_nodes[0],level)
    elif level == 0:
        print "Computing first level"
        for i in range(full_size//128):
            value = utils.sha3( dataset_lookup[i] + dataset_lookup[i+1] )
            node = MerkleNode( True, value, None, None )
            level_nodes.append(node)
            if i % 1000 == 0:
                print "level 0, element " + str(i)
    else:
        print "computing level " + str(level)
        size = len(prev_level_nodes)
        for i in range(size//2):
            right = None
            if 2*i+1 >= size:
                right = MerkleNode( True, 0, None, None )
            else:
                right = prev_level_nodes[2*i+1]
            left = prev_level_nodes[2*i]
            node = MerkleNode(False,0,left,right)
            
            print "level 0, element " + str(i)            
            
    return compute_cache_merkle_tree(full_size,dataset_lookup,level+1,level_nodes)
          


raw_rlp = "f902a0f9020da0cdcbe20df89a1a82b695088449025409da9f8051cc4078eddfbed5df8d303b4ea01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347944bb96091ee9d802ed039c4d1a5f6216f90f81b01a0fdc095b1def486fbfacd7059c5b6a1476662d6a93585773f879c8bd9a0122a07a0893bd1437053554da16fd268cbd197b37ea8974b87ebe3fc8025d3a64a869f93a06840c0608508973ef71f9f5cd9b1026817bac20fd30e62df424c475cd5195011b9010000000000000000000000000000000000000000000000000000000000000020000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000120000000000200000000000000000000000000000000000000000000000000000000000000000866b6e77e6b764832fcfff833dc951830100c88458986a4d8d657468706f6f6c202d20555331a0f9e6ef14b97cc29b289b306fd9e70382d7b8f9cca7f3ee791bb4f79637698e5c88278867b1e4ea6850f88df88b82cc688504a817c800830e57e094cd111aa492a9c77a367c36e6d6af8e6f212e0c8e80a4e1fa8e843f0e24ef6cfc2af7206e8f8f7beecaeef824f68ba237007e001e1233b1b14a381ba0a21789dc109bd6630c955930ab2630a2b9c4b7bb0a8934bedc17144f8567defba07b03e650fe72bada0f047645f03344f4449a449e2688c080f02248bc0c874acfc0"
print str(len(raw_rlp)//2) 
header = blocks.BlockHeader.from_block_rlp(h2b(raw_rlp))

print str(header.to_dict())
print str(header.check_pow())
print b2h(header.mining_hash)

#8fb9d5aa5aa693ad8d5af51314db64ceb400bab44d916b8780d4dac1e135ac61

'''
nonce = 0x278867b1e4ea6850
hash = ecfae06ad0b42694c600e349144441fe17570b4225c5a4d3e376b775bf620dec
block_number = 3133439
'''

'''
        return utils.sha3(rlp.encode(self, BlockHeader.exclude(['mixhash', 'nonce'])))
    "second": {
        "nonce": "307692cf71b12f6d", 
        "mixhash": "e55d02c555a7969361cf74a9ec6211d8c14e4517930a00442f171bdb1698d175", 
        "header": "f901f7a01bef91439a3e070a6586851c11e6fd79bbbea074b2b836727b8e75c7d4a6b698a01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d4934794ea3cb5f94fa2ddd52ec6dd6eb75cf824f4058ca1a00c6e51346be0670ce63ac5f05324e27d20b180146269c5aab844d09a2b108c64a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421a056e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421b90100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000008302004002832fefd880845511ed2a80a0e55d02c555a7969361cf74a9ec6211d8c14e4517930a00442f171bdb1698d17588307692cf71b12f6d", 
        "seed": "0000000000000000000000000000000000000000000000000000000000000000", 
        "result": "ab9b13423cface72cbec8424221651bc2e384ef0f7a560e038fc68c8d8684829", 
        "cache_size": 16776896, 
        "full_size": 1073739904, 
        "header_hash": "100cbec5e5ef82991290d0d93d758f19082e71f234cf479192a8b94df6da6bfe", 
        "cache_hash": "35ded12eecf2ce2e8da2e15c06d463aae9b84cb2530a00b932e4bbc484cde353"
    }
'''
















    
#1744829056        
'''
for block_number in range(100):
    block_number = block_number * EPOCH_LENGTH 
    full_size = get_full_size(block_number)
    cache_size = get_cache_size(block_number)
    if full_size == 1744829056:
        print "\n"
        print "1744829056"
        print str(full_size)
        print str(block_number)
'''

#print b2h(utils.sha3(h2b("100cbec5e5ef82991290d0d93d758f19082e71f234cf479192a8b94df6da6bfe")[::-1]))

#sd

#print "full size = " + str(full_size//128)
#sd 
 
 
 
block_number = 3133439
 
block_number = 3133439#2400000
full_size = get_full_size(block_number)
print "full size = " + str(full_size//128)


seed = get_seedhash(block_number)
cache_size = get_cache_size(block_number)
print "making cache"
#cache = mkcache(cache_size, seed)
#cache_file = open('cache.dat', 'w')
#pickle.dump(cache,cache_file)

cache_file = open('cache.dat', 'r')
cache = pickle.load(cache_file)
cache_file.close()
print "done"


#[5ed8bead,3bfaa00e,24f8a313,c0a3a5ad,36f9db35,ac4ad790,dc04492f,67fffca1,0e2967ad,e3abc551,c0933ae0,e64318c,f88ded2cd,334b2a54,6e17128d,c0509a60]

#header = h2b("c7670049269c10462d3c5e86f42c60309eed72602fc1e6185efbba44328b9218")[::-1]
#nonce = h2b("a8e9c2db86671707")

              
#header = h2b("100cbec5e5ef82991290d0d93d758f19082e71f234cf479192a8b94df6da6bfe")#[::-1]
#nonce = h2b("307692cf71b12f6d")

header = h2b("ecfae06ad0b42694c600e349144441fe17570b4225c5a4d3e376b775bf620dec")
nonce = h2b("278867b1e4ea6850")[::-1]

'''
result = calc_dataset_item(cache,13282552*2)
for i in range(len( result ) ):
    print "%08x" % result[i]

result = calc_dataset_item(cache,13282552*2 + 1)
for i in range(len( result ) ):
    print "%08x" % result[i]

sd
'''
hash = hashimoto_light(full_size, cache, header, nonce)


#print str(hash)
result = hash["result"]
#print str(result)
print b2h(result)
sd
#0x73c2bd54c3ee10eb8e4a7f663bdc01da272292802b7c1b4ec713271fd034ca4e
print str(elements_input_for_contract)

sd

sd
print "full size = " + str(full_size)
#{'mix digest': '\x13\xaa\xa1\xe4\xac8L\xd5\xda1+\x12\xd5\x86\x00uH\xef>~\x9b3\xf0\xdf\x82}\x87\x07\xd3\x16\xf4b', 'result': "\x97\x90z'\xe6\xc9\\I\x16cG\x82)\x8eh\x1f\x0e:\x99}\x97r\xa9\x15\x07\xed]k\xae\xac\xcf@"}
#{'mix digest': '\x13\xaa\xa1\xe4\xac8L\xd5\xda1+\x12\xd5\x86\x00uH\xef>~\x9b3\xf0\xdf\x82}\x87\x07\xd3\x16\xf4b', 'result': "\x97\x90z'\xe6\xc9\\I\x16cG\x82)\x8eh\x1f\x0e:\x99}\x97r\xa9\x15\x07\xed]k\xae\xac\xcf@"}



#0x1f2c31d8b8b88d9590f4fad7c0aebeb5fa5a443dad97c2c3e8e81e28593942a3

'''
0x35ceec90
0xefa1019c
0x189199f3
0xbdba9887
'''


#[5ed8bead,3bfaa00e,24f8a313,c0a3a5ad,36f9db35,ac4ad790,dc04492f,67fffca1,0e2967ad,e3abc551,c0933ae0,e64318c,f88ded2cd,334b2a54,6e17128d,c0509a60]
#5ed8bead
#adbed85e 0ea0fa3b13a3f824ada5a3c035dbf93690d74aac2f4904dca1fcff67ad67290e51c5abe3e03a93c0cf1843e6cdd2de88542a4b338d12176e609a50c09702ab9dfc093f18c31201969ad4da379affc4693f106efb30746b43bdd4e09b7b3fd3b85f0c53f9d47088938300ed8836c32c8bed9d4213ce8e264ec73bb2f5


#0x73c2bd54c3ee10eb8e4a7f663bdc01da272292802b7c1b4ec713271fd034ca4e
