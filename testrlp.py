from pycoin.serialize import b2h, h2b
from pycoin import encoding
import rlp
from ethereum import tester, utils, abi, blocks, transactions
import requests
import json
import jsonrpc
import time
from ethereum.abi import ContractTranslator
from ethereum.utils import mk_contract_address
from bike.parsing.fastparserast import Node


global_wait_for_confirm = True
use_ether_scan = False
use_augor = False
ether_scan_api_key = '66FCG5X3HSVW23R2ZJTFJEKWMKKGJVIQXK'
local_url = "http://localhost:8545/jsonrpc"
augor_local_url = "https://eth3.augur.net/jsonrpc"

def merge_two_dicts(x, y):
    '''Given two dicts, merge them into a new dict as a shallow copy.'''
    z = x.copy()
    z.update(y)
    return z

def etherscan_call(method_name, params):
    url = "https://testnet.etherscan.io/api"
    payload = {"module" : "proxy",
               "action" : method_name,
               "apikey" : ether_scan_api_key }
    payload = merge_two_dicts(payload, params[0])
    response = requests.post(url, params=payload)
    return response.json()[ 'result' ]
    
    
def json_call(method_name, params):
    if use_ether_scan:
        return etherscan_call(method_name, params)
    url = local_url
    if use_augor:
        url = augor_local_url
    headers = {'content-type': 'application/json'}
    
    # Example echo method
    payload = { "method": method_name,
                "params": params,
                "jsonrpc": "2.0",
                "id": 1,
                }
    # print str(params)
    response = requests.post(url, data=json.dumps(payload), headers=headers).json()
    # print str(response)
    print response
    return response[ 'result' ]

global_nonce = -1
def get_num_transactions(address):
    global global_nonce
    # if( global_nonce > 0 ):
    #    global_nonce += 1
    #    return "0x" + "%x" % global_nonce
    if use_ether_scan:
        params = [{ "address" : "0x" + address, "tag" : "pending" }]
    else:
        params = [ "0x" + address, "pending" ]
    nonce = json_call("eth_getTransactionCount", params)
    # print "nonce: " + str(nonce)
    global_nonce = int(nonce, 16)
    return nonce 

def get_gas_price_in_wei():
    if use_ether_scan:
        return "0x%x" % 20000000000  # 20 gwei
    return json_call("eth_gasPrice", [])

def eval_startgas(src, dst, value, data, gas_price):
    if use_ether_scan or True:
        return "0x%x" % (4712388 / 2)  # hardcoded max gas
        
    params = { "value" : "0x" + str(value),
               "pasPrice" : gas_price }
    if len(data) > 0:
        params["data"] = "0x" + str(data)
    if len(dst) > 0:
        params["to"] = "0x" + dst
    #           "from" : "0x" + dst }
    # params = { "from" : "0x06f099a7d789f10b0c1c1f069638ba25b2bf8483",
    #           "data" : "123456789" }
    # print str(params)
    return json_call("eth_estimateGas", [params])

def make_transaction(src_priv_key, dst_address, value, data):
    src_address = b2h(utils.privtoaddr(src_priv_key))
    nonce = get_num_transactions(src_address)
    gas_price = get_gas_price_in_wei()
    data_as_string = b2h(data)
    # print len(data_as_string)
    # if len(data) > 0:
    #    data_as_string = "0x" + data_as_string 
    start_gas = eval_startgas(src_address, dst_address, value, data_as_string, gas_price)
    
    nonce = int(nonce, 16)
    gas_price = int(gas_price, 16)
    start_gas = int(start_gas, 16) + 100000
    
    start_gas = 7612288  # // 10
    # start_gas = 5000000    
    
    tx = transactions.Transaction(nonce,
                                   gas_price,
                                   start_gas,
                                   dst_address,
                                   value,
                                   data).sign(src_priv_key)
    
    
                                   
    tx_hex = b2h(rlp.encode(tx))
    tx_hash = b2h(tx.hash)
    print(tx_hex)
    # print str(tx_hash)
    if use_ether_scan:
        params = [{"hex" : "0x" + tx_hex }]
    else:
        params = ["0x" + tx_hex]
    return_value = json_call("eth_sendRawTransaction", params)                       
    if return_value == "0x0000000000000000000000000000000000000000000000000000000000000000":
        print "Transaction failed"
        return return_value
    wait_for_confirmation(tx_hash)
    return return_value        
    
def get_contract_data(contract_name, ctor_args):
    bin_file = open(contract_name + ".bin", "rb")
    bin = h2b(bin_file.read())
    # print bin
    bin_file.close()
    
    abi_file = open(contract_name + ".abi", "r")
    abi = abi_file.read()
    abi_file.close()
    
    translator = ContractTranslator(abi)
    ctor_call = translator.encode_constructor_arguments(ctor_args)
    # print "ctor"
    # print b2h(ctor_call)
    
        
    return (bin + ctor_call, abi)
    
def upload_contract(priv_key, contract_data, value):
    src_address = b2h(utils.privtoaddr(priv_key))
    nonce = get_num_transactions(src_address)
    gas_price = get_gas_price_in_wei()
    start_gas = eval_startgas(src_address, "", value, b2h(contract_data), gas_price)    
    
    contract_hash = b2h(mk_contract_address(src_address, int(nonce, 16))) 
    print "contract hash"
    print contract_hash
    
    nonce = int(nonce, 16)
    # print str(nonce)
    gas_price = int(gas_price, 16)
    start_gas = int(start_gas, 16) + 100000
    print str(start_gas)
    start_gas = 3712288  # 4710388#3000000#4712388 # 5183626 / 2
    
    tx = transactions.contract(nonce, gas_price, start_gas, value, contract_data).sign(priv_key)
                     
    # print contract_data                  
    tx_hex = b2h(rlp.encode(tx))
    tx_hash = b2h(tx.hash)
    print(tx_hex)
    print tx_hash
    
    # print str(tx_hash)
    if use_ether_scan:
        params = [{"hex" : "0x" + tx_hex }]
    else:
        params = ["0x" + tx_hex]
            
    return_value = (json_call("eth_sendRawTransaction", params), contract_hash)
    wait_for_confirmation(tx_hash)
    return return_value        

def call_function(priv_key, value, contract_hash, contract_abi, function_name, args):
    translator = ContractTranslator(contract_abi)
    call = translator.encode_function_call(function_name, args)
    return make_transaction(priv_key, contract_hash, value, call)
    

def call_const_function(priv_key, value, contract_hash, contract_abi, function_name, args):
    src_address = b2h(utils.privtoaddr(priv_key))    
    translator = ContractTranslator(contract_abi)
    call = translator.encode_function_call(function_name, args)  
    nonce = get_num_transactions(src_address)
    gas_price = get_gas_price_in_wei()
    
    start_gas = eval_startgas(src_address, contract_hash, value, b2h(call), gas_price)    
    nonce = int(nonce, 16)
    gas_price = int(gas_price, 16)
    start_gas = int(start_gas, 16) + 100000
    start_gas = 7612288 

    
    params = { "from" : "0x" + src_address,
               "to"   : "0x" + contract_hash,
               "gas"  : "0x" + "%x" % start_gas,
               "gasPrice" : "0x" + "%x" % gas_price,
               "value" : "0x" + str(value),
               "data" : "0x" + b2h(call) }
    
    return_value = json_call("eth_call", [params])
    print return_value
    return_value = h2b(return_value[2:])  # remove 0x
    return translator.decode(function_name, return_value)



def make_new_filter(contract_address, topic):
    params = { "fromBlock" : "0x1",
               "address": "0x" + contract_address,
               "topics" : [topic] }
    filter_id = json_call("eth_newFilter", [params])
    # filter_id = "0x0"
    print filter_id
    params = filter_id
    print json_call("eth_getFilterLogs", [params])

def wait_for_confirmation(tx_hash):
    return
    params = None
    if use_ether_scan:
        params = { "txhash" : "0x" + tx_hash }
    else:
        params = "0x" + tx_hash
    round = 0
    while(True):
        print "waiting for confirmation round " + str(round)
        round += 1 
        result = json_call("eth_getTransactionReceipt", [params])
        # print result
        if result is None:
            if(global_wait_for_confirm):
                time.sleep(10)
                continue
            else:
                time.sleep(1)
                return                
        # print str(result["blockHash"])
        if not(result["blockHash"] is None):
            return result
        time.sleep(10)
        
        
    
################################################################################

def augmented_node(left_child_int, right_child_int, min_timestamp_int, max_timestamp_int):
    left_child_hex = ("%0.32x" % left_child_int).zfill(64)
    right_child_hex = ("%0.32x" % right_child_int).zfill(64)
    children_hex = left_child_hex + right_child_hex  
    hash_int = int(b2h(utils.sha3(h2b(children_hex))), 16) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
    
    node_hex = ("%0.16x" % hash_int).zfill(32) + ("%0.4x" % max_timestamp_int).zfill(8) + ("%0.4x" % min_timestamp_int).zfill(8)
        
    node_int = int(node_hex, 16)
    
    return node_int  
    
def augmented_leaf(block_header_hex, timestamp_int):
    block_header_int = int(b2h(utils.sha3(h2b(block_header_hex))), 16)
    return augmented_node(block_header_int, block_header_int, timestamp_int, timestamp_int)
         
# build branch 000...0000         
def augmented_branch_zero(block_header_hex, timestamp_int, height):
    branch = []
    sybil = []
    leaf = augmented_leaf(block_header_hex, timestamp_int)
    branch.append(leaf)
    last_in_branch = leaf
    dummy_sybil = int("ff" * 32, 16)
    for i in range(height):
        node = augmented_node(last_in_branch, dummy_sybil, timestamp_int, 0xffffffff)
        branch.append(node)
        sybil.append(dummy_sybil)
        last_in_branch = node

    branch.reverse()
    sybil.reverse()
    
    return (branch, sybil)
    
################################################################################

def block_branch_zero(coinbase_tx_hex, height):
    branch = []
    sybil = []
    leaf = encoding.double_sha256(h2b(coinbase_tx_hex))
    dummy_sybil = h2b("ab" * 32)
    branch.append(int(b2h(leaf), 16))
    last_node = leaf
    for i in range(height):
        concat_hex = b2h(last_node).zfill(64) + b2h(dummy_sybil)
        node_hex = b2h(encoding.double_sha256(h2b(concat_hex)))
        sybil.append(int(b2h(dummy_sybil), 16))
        branch.append(int(node_hex, 16))
        last_node = h2b(node_hex)

    branch.reverse()
    sybil.reverse()
    
    return (branch, sybil)

def generate_block_header_hex(merkle_root_int, timestamp_int):
    nonce = 0
    merkle_hex = ("%0.32x" % merkle_root_int).zfill(64)
    timestamp_hex = ("%0.4x" % timestamp_int).zfill(8)
    header_hex = "00" * 36 + merkle_hex + timestamp_hex + "00" * 4
    
    while(True):
        nonce_hex = ("%0.4x" % nonce).zfill(8)
        result_header_hex = header_hex + nonce_hex
        sha = int(b2h(encoding.double_sha256(h2b(result_header_hex))), 16)
        if(sha & 0x03 == 0):
            return result_header_hex
        nonce += 1
        
        
    return None
        
################################################################################

def generate_verification_params(aug_height, merkle_height, coinbase_tx_hex_middle, coinbase_tx_hex_end):
    timestamp_int = 1
    coinbase_tx_hex = coinbase_tx_hex_middle + coinbase_tx_hex_end
    (block_merkle_branch, block_sibils) = block_branch_zero(coinbase_tx_hex, merkle_height)
    block_header_hex = generate_block_header_hex(block_merkle_branch[0], timestamp_int)
    (aug_branch, aug_sibils) = augmented_branch_zero(block_header_hex, timestamp_int, aug_height)
    seed = int("ff" * 32, 16)
    timestampIndex = 0
    coinbase_middle = h2b(coinbase_tx_hex_middle)
    
    return [aug_branch, aug_sibils, seed, block_merkle_branch, block_sibils, h2b(block_header_hex), coinbase_middle, timestampIndex]

def prepare_first_run(tx_suf_hex, contract_hash, abi):
    
    global global_wait_for_confirm
    global_origin_value = global_wait_for_confirm 
    length = len(tx_suf_hex) // 2
    # length -= 6400 # already uploaded
    if((length % 3200) > 0):
        raise "Invalid length"
    num_iters = length // 3200
    for i in range(num_iters):
        print "debug_extendCoinbaseTxOutput"
        # global_wait_for_confirm = ((i % 3 ) == 0)
        print call_function(key, 0, contract_hash, abi, "debug_extendCoinbaseTxOutput", [0, 3200])
        print "(" + str(i) + "/" + str(num_iters) + ")"
    global_wait_for_confirm = global_origin_value
        
    print "register"
    print call_function(key, 0, contract_hash, abi, "register", [0xdeadbeef])


def prepare_contract_env(num_shares, aug_merkle, contract_hash, abi):
    print "submitShares"    
    print call_function(key, 0, contract_hash, abi, "submitShares", [aug_merkle, num_shares])         
         

################################################################################

def submit_full_block(coinbase_prefix, merkle_branch, sibil, blockHeader, timestampindex):
    params = [coinbase_prefix, merkle_branch, sibil, blockHeader]
    prev_block = blockHeader
    for index in range(1, 6):
        header_hex = "ff" * 4 + b2h(encoding.double_sha256(prev_block)) + (40 * "ff")
        nonce = 0
        while(True):
            nonce_hex = ("%0.4x" % nonce).zfill(8)
            result_header_hex = header_hex + nonce_hex
            sha = int(b2h(encoding.double_sha256(h2b(result_header_hex))), 16)
            if(sha & 0x03 == 0):
                header_hex = result_header_hex 
                break
            nonce += 1
        header = h2b(header_hex)
        params.append(header)
        prev_block = header
    
    print "submitFullBlock"
    params.append(timestampindex)
    call_function(key, 0, contract_hash, abi, "submitFullBlock", params)    
            
################################################################################            
        
def payment_request():
    print "requestPayment"
    print call_function(key, 0, contract_hash, abi, "requestPayment", [0, 2])
    print "constructCoinbaseTx"        
    print call_function(key, 0, contract_hash, abi, "constructCoinbaseTx", [2])    


################################################################################






################################################################################


if( use_augor or use_ether_scan ):
    key = utils.sha3("Smart Pool2")
else:
    key = h2b("4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d")
address = b2h(utils.privtoaddr(key))


global_wait_for_confirm = True
# ( contract_data, abi ) = get_contract_data( "./DumbPool", [])#,24,5,2016] )


# print address
# global_wait_for_confirm = True
# ( contract_data, abi ) = get_contract_data( "./SmartPool", [])#,24,5,2016] )



#(contract_data_ethash, abi_ethash) = get_contract_data("./RLPReaderTest", [])  # ,24,5,2016] )
(contract_data_ethash, abi_ethash) = get_contract_data("./Agt", [])  # ,24,5,2016] )

contract_hash_ethash = None
use_augor = False
use_ether_scan = False
#(str, contract_hash_ethash) = upload_contract( key, contract_data_ethash, 0 )
#xsd


contract_hash_ethash = "a586074fa4fe3e546a132a16238abe37951d41fe"
'''
params = [0x000000005832b627a4c7fb2e4480ca3e000000005832b627a4c7fb2e4480ca3e,
          0x000000000000000000000000000000003ef5bf416a87e54c8a4b249ebcb5c92f,
          0x000000005832b628e07321b4ef5633ba000000005832b628e07321b4ef5633ba,
          0x00000000000000000000000000000000f7ada6f453d1cfd9f77584997ad1c5c6]

result = call_const_function(key, 0, contract_hash_ethash, abi_ethash, "hash4", params)[0]
print "0x%x" % result[i]



min = h2b("5832b627a4c7fb2e4480ca3e")[::-1]
max = h2b("5832b628e07321b4ef5633ba")[::-1]

left = h2b("3ef5bf416a87e54c8a4b249ebcb5c92f")#[::-1]
right = h2b("f7ada6f453d1cfd9f77584997ad1c5c6")#[::-1]

zero = h2b("00")

result = utils.sha3(zero * 20 + min + zero * 16 + left + zero * 20 + max + zero * 16 + right)
print b2h(result)

sd
'''

raw_rlp = "f902a0f9020da0cdcbe20df89a1a82b695088449025409da9f8051cc4078eddfbed5df8d303b4ea01dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347944bb96091ee9d802ed039c4d1a5f6216f90f81b01a0fdc095b1def486fbfacd7059c5b6a1476662d6a93585773f879c8bd9a0122a07a0893bd1437053554da16fd268cbd197b37ea8974b87ebe3fc8025d3a64a869f93a06840c0608508973ef71f9f5cd9b1026817bac20fd30e62df424c475cd5195011b9010000000000000000000000000000000000000000000000000000000000000020000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000120000000000200000000000000000000000000000000000000000000000000000000000000000866b6e77e6b764832fcfff833dc951830100c88458986a4d8d657468706f6f6c202d20555331a0f9e6ef14b97cc29b289b306fd9e70382d7b8f9cca7f3ee791bb4f79637698e5c88278867b1e4ea6850f88df88b82cc688504a817c800830e57e094cd111aa492a9c77a367c36e6d6af8e6f212e0c8e80a4e1fa8e843f0e24ef6cfc2af7206e8f8f7beecaeef824f68ba237007e001e1233b1b14a381ba0a21789dc109bd6630c955930ab2630a2b9c4b7bb0a8934bedc17144f8567defba07b03e650fe72bada0f047645f03344f4449a449e2688c080f02248bc0c874acfc0"
print str(len(raw_rlp)//2) 
header = blocks.BlockHeader.from_block_rlp(h2b(raw_rlp))

# exclude mix hash and nonce
new_header = rlp.encode(header, blocks.BlockHeader.exclude(['nonce', 'mixhash']))
#print str(new_header)
#new_header = rlp.decode(new_header)
#print str(new_header)
#sd

therlp = rlp.decode(h2b(raw_rlp))
print str(len(therlp))
rpl_header = therlp[0]
rlp_header_bytes = rlp.encode(rpl_header)
print len(rlp_header_bytes)
print b2h(utils.sha3(rlp_header_bytes))

#print b2h((therlp[0])[14])

print str(header.to_dict())




rlp_input = rlp_header_bytes
params = [rlp_input,14]


'''
    function verifyAgt( uint   leaf32BytesHash,
                        uint   leafCounter,
                        uint   branchIndex,
                        uint[] countersBranch,
                        uint[] hashesBranch ) constant returns(bool) {

'''


counterBranch = [0x000000005832b629a23dc089f2b1f52b000000005832b629a23dc089f2b1f52a, 0x000000005832b629a23dc089f2b1f52b000000005832b629a23dc089f2b1f52a, 0x000000005832b628e07321b4ef5633ba000000005832b6257d7d61877ceccac5]
hashesBranch = [0x00000000000000000000000000000000e52d291c15730286610ce9b15b6bef06, 0x000000000000000000000000000000000e1b2083b15f09d5bdabe457dbe4628b, 0x0000000000000000000000000000000079cc6a8e0e1e0cce54034f729de49cd8]

print len(counterBranch)
print len(hashesBranch)

params = [0xe52d291c15730286610ce9b15b6bef06,0x5832b629a23dc089f2b1f527,4,counterBranch,hashesBranch]

result = call_const_function(key, 0, contract_hash_ethash, abi_ethash, "verifyAgt", params)[0]
for i in range(len(result)):
    print "0x%x" % result[i]
sd



result = call_function(key, 0, contract_hash_ethash, abi_ethash, "test", [new_header])[0]
for i in range(len(result)):
    print "0x%x" % result[i]


print b2h(utils.sha3(new_header))

sd


#{'nonce': '0x278867b1e4ea6850', 'prevhash': '0xcdcbe20df89a1a82b695088449025409da9f8051cc4078eddfbed5df8d303b4e', 'state_root': 'fdc095b1def486fbfacd7059c5b6a1476662d6a93585773f879c8bd9a0122a07', 'difficulty': '118122202183524', 'mixhash': '0xf9e6ef14b97cc29b289b306fd9e70382d7b8f9cca7f3ee791bb4f79637698e5c', 'number': '3133439', 'gas_used': '65736', 'coinbase': '4bb96091ee9d802ed039c4d1a5f6216f90f81b01', 'tx_list_root': '893bd1437053554da16fd268cbd197b37ea8974b87ebe3fc8025d3a64a869f93', 'receipts_root': '6840c0608508973ef71f9f5cd9b1026817bac20fd30e62df424c475cd5195011', 'timestamp': '1486383693', 'uncles_hash': '0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347', 'extra_data': '0x657468706f6f6c202d20555331', 'bloom': '00000000000000000000000000000000000000000000000000000000000020000000000000000000000000040000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000120000000000200000000000000000000000000000000000000000000000000000000000000000', 'gas_limit': '4049233'}

#4bb96091ee9d802ed039c4d1a5f6216f90f81b01
#0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347 # mismatch





