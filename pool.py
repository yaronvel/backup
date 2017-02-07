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

def etherscan_call( method_name, params ):
    url = "https://testnet.etherscan.io/api"
    payload = {"module" : "proxy",
               "action" : method_name,
               "apikey" : ether_scan_api_key }
    payload = merge_two_dicts(payload, params[0] )
    response = requests.post( url, params=payload )
    return response.json()[ 'result' ]
    
    
def json_call( method_name, params ):
    if use_ether_scan:
        return etherscan_call( method_name, params )
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
    #print str(params)
    response = requests.post(url, data=json.dumps(payload), headers=headers).json()
    #print str(response)
    return response[ 'result' ]

global_nonce = -1
def get_num_transactions( address ):
    global global_nonce
    if( global_nonce > 0 ):
        global_nonce += 1
        return "0x" + "%x" % global_nonce
    if use_ether_scan:
        params = [{ "address" : "0x" + address, "tag" : "pending" }]
    else:
        params = [ "0x" + address, "pending" ]
    nonce = json_call( "eth_getTransactionCount", params )
    #print "nonce: " + str(nonce)
    global_nonce = int(nonce,16)
    return nonce 

def get_gas_price_in_wei( ):
    if use_ether_scan:
        return "0x%x" % 20000000000 # 20 gwei
    return json_call( "eth_gasPrice", [] )

def eval_startgas( src, dst, value, data, gas_price ):
    if use_ether_scan or True:
        return "0x%x" % (4712388/2) # hardcoded max gas
        
    params = { "value" : "0x" + str(value),
               "pasPrice" : gas_price }
    if len(data) > 0:
        params["data"] = "0x" + str(data)
    if len(dst) > 0:
        params["to"] = "0x" + dst
    #           "from" : "0x" + dst }
    #params = { "from" : "0x06f099a7d789f10b0c1c1f069638ba25b2bf8483",
    #           "data" : "123456789" }
    #print str(params)
    return json_call( "eth_estimateGas", [params] )

def make_transaction( src_priv_key, dst_address, value, data ):
    src_address = b2h( utils.privtoaddr(src_priv_key) )
    nonce = get_num_transactions( src_address )
    gas_price = get_gas_price_in_wei()
    data_as_string = b2h(data)
    #print len(data_as_string)
    #if len(data) > 0:
    #    data_as_string = "0x" + data_as_string 
    start_gas = eval_startgas( src_address, dst_address, value, data_as_string, gas_price )
    
    nonce = int( nonce, 16 )
    gas_price = int( gas_price, 16 )
    start_gas = int( start_gas, 16 ) + 100000
    
    start_gas  = 3300000# // 10
    #start_gas = 5000000    
    
    tx = transactions.Transaction( nonce,
                                   gas_price,
                                   start_gas,
                                   dst_address,
                                   value,
                                   data ).sign(src_priv_key)
    
    
                                   
    tx_hex  = b2h(rlp.encode(tx))
    tx_hash = b2h( tx.hash )
    print(tx_hex)
    #print str(tx_hash)
    if use_ether_scan:
        params = [{"hex" : "0x" + tx_hex }]
    else:
        params = ["0x" + tx_hex]
    return_value = json_call( "eth_sendRawTransaction", params )                       
    if return_value == "0x0000000000000000000000000000000000000000000000000000000000000000":
        print "Transaction failed"
        return return_value
    wait_for_confirmation(tx_hash)
    return return_value        
    
def get_contract_data( contract_name, ctor_args ):
    bin_file = open( contract_name + ".bin", "rb" )
    bin = h2b( bin_file.read() )
    #print bin
    bin_file.close()
    
    abi_file = open( contract_name + ".abi", "r" )
    abi = abi_file.read()
    abi_file.close()
    
    translator = ContractTranslator(abi)
    ctor_call = translator.encode_constructor_arguments( ctor_args )
    #print "ctor"
    #print b2h(ctor_call)
    
        
    return (bin + ctor_call,abi)
    
def upload_contract( priv_key, contract_data, value ):
    src_address = b2h( utils.privtoaddr(priv_key) )
    nonce = get_num_transactions( src_address )
    gas_price = get_gas_price_in_wei()
    start_gas = eval_startgas( src_address, "", value, b2h(contract_data), gas_price )    
    
    contract_hash = b2h(mk_contract_address(src_address,int(nonce,16))) 
    print "contract hash"
    print contract_hash
    
    nonce = int( nonce, 16 )
    gas_price = int( gas_price, 16 )
    start_gas = int( start_gas, 16 ) + 100000
    print str(start_gas)
    start_gas =  3223680#4710388#3000000#4712388 # 5183626 / 2
    
    tx = transactions.contract(nonce, gas_price, start_gas, value,contract_data).sign(priv_key)
                     
    #print contract_data                  
    tx_hex  = b2h(rlp.encode(tx))
    tx_hash = b2h( tx.hash )
    print(tx_hex)
    print tx_hash
    
    #print str(tx_hash)
    if use_ether_scan:
        params = [{"hex" : "0x" + tx_hex }]
    else:
        params = ["0x" + tx_hex]
            
    return_value = ( json_call( "eth_sendRawTransaction", params), contract_hash )
    wait_for_confirmation(tx_hash)
    return return_value        

def call_function( priv_key, value, contract_hash, contract_abi, function_name, args ):
    translator = ContractTranslator(contract_abi)
    call = translator.encode_function_call(function_name, args)
    return make_transaction(priv_key, contract_hash, value, call)
    

def call_const_function( priv_key, value, contract_hash, contract_abi, function_name, args ):
    src_address = b2h( utils.privtoaddr(priv_key) )    
    translator = ContractTranslator(contract_abi)
    call = translator.encode_function_call(function_name, args)  
    nonce = get_num_transactions( src_address )
    gas_price = get_gas_price_in_wei()
    
    start_gas = eval_startgas( src_address, contract_hash, value, b2h(call), gas_price )    
    nonce = int( nonce, 16 )
    gas_price = int( gas_price, 16 )
    start_gas = int( start_gas, 16 ) + 100000
    
    params = { "from" : "0x" + src_address,
               "to"   : "0x" + contract_hash,
               "gas"  : "0x" + str(start_gas),
               "gasPrice" : "0x" + str(gas_price),
               "value" : "0x" + str(value),
               "data" : "0x" + b2h(call) }
    
    return_value = json_call( "eth_call", [params])
    return_value = h2b(return_value[2:]) # remove 0x
    return translator.decode(function_name, return_value)



def make_new_filter( contract_address, topic ):
    params = { "fromBlock" : "0x1",
               "address": "0x" + contract_address,
               "topics" : [topic] }
    filter_id = json_call("eth_newFilter", [params])
    #filter_id = "0x0"
    print filter_id
    params = filter_id
    print json_call("eth_getFilterLogs", [params])

def wait_for_confirmation( tx_hash ):
    params = None
    if use_ether_scan:
        params = { "txhash" : "0x" + tx_hash }
    else:
        params = "0x" + tx_hash
    round = 0
    while( True ):
        print "waiting for confirmation round " + str(round)
        round += 1 
        result = json_call( "eth_getTransactionReceipt", [params] )
        #print result
        if result is None:
            if( global_wait_for_confirm ):
                time.sleep(10)
                continue
            else:
                time.sleep(1)
                return                
        #print str(result["blockHash"])
        if not( result["blockHash"] is None ):
            return result
        time.sleep(10)
        
        
    
################################################################################

def augmented_node( left_child_int, right_child_int, min_timestamp_int, max_timestamp_int):
    left_child_hex = ("%0.32x" % left_child_int).zfill(64)
    right_child_hex = ("%0.32x" % right_child_int).zfill(64)
    children_hex = left_child_hex + right_child_hex  
    hash_int = int( b2h(utils.sha3(h2b(children_hex))), 16 ) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
    
    node_hex = ("%0.16x" % hash_int).zfill(32) +  ("%0.4x" % max_timestamp_int).zfill(8) + ("%0.4x" % min_timestamp_int).zfill(8)
        
    node_int = int(node_hex, 16)
    
    return node_int  
    
def augmented_leaf( block_header_hex, timestamp_int ):
    block_header_int = int( b2h(utils.sha3( h2b( block_header_hex ) )), 16 )
    return augmented_node(block_header_int, block_header_int, timestamp_int, timestamp_int)
         
# build branch 000...0000         
def augmented_branch_zero( block_header_hex, timestamp_int, height ):
    branch = []
    sybil = []
    leaf =  augmented_leaf( block_header_hex, timestamp_int )
    branch.append(leaf)
    last_in_branch = leaf
    dummy_sybil = int( "ff" * 32, 16 )
    for i in range(height):
        node = augmented_node(last_in_branch, dummy_sybil, timestamp_int, 0xffffffff )
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
    dummy_sybil = h2b( "ab" * 32 )
    branch.append(int(b2h(leaf),16))
    last_node = leaf
    for i in range(height):
        concat_hex = b2h(last_node).zfill(64) + b2h(dummy_sybil)
        node_hex = b2h(encoding.double_sha256(h2b(concat_hex)))
        sybil.append(int(b2h(dummy_sybil),16))
        branch.append(int(node_hex,16))
        last_node = h2b(node_hex)

    branch.reverse()
    sybil.reverse()
    
    return (branch, sybil)

def generate_block_header_hex( merkle_root_int, timestamp_int ):
    nonce = 0
    merkle_hex = ("%0.32x" % merkle_root_int).zfill(64)
    timestamp_hex = ("%0.4x" % timestamp_int).zfill(8)
    header_hex = "00" * 36 + merkle_hex + timestamp_hex + "00" * 4
    
    while( True ):
        nonce_hex = ("%0.4x" % nonce).zfill(8)
        result_header_hex = header_hex + nonce_hex
        sha = int(b2h(encoding.double_sha256(h2b(result_header_hex))),16)
        if( sha & 0x03 == 0 ):
            return result_header_hex
        nonce += 1
        
        
    return None
        
################################################################################

def generate_verification_params( aug_height, merkle_height, coinbase_tx_hex_middle, coinbase_tx_hex_end ):
    timestamp_int = 1
    coinbase_tx_hex = coinbase_tx_hex_middle + coinbase_tx_hex_end
    (block_merkle_branch,block_sibils) = block_branch_zero(coinbase_tx_hex, merkle_height)
    block_header_hex = generate_block_header_hex( block_merkle_branch[0], timestamp_int )
    (aug_branch, aug_sibils) = augmented_branch_zero( block_header_hex, timestamp_int, aug_height )
    seed = int( "ff" * 32, 16)
    timestampIndex = 0
    coinbase_middle = h2b(coinbase_tx_hex_middle)
    
    return [aug_branch,aug_sibils,seed,block_merkle_branch,block_sibils,h2b(block_header_hex),coinbase_middle,timestampIndex]

def prepare_first_run( tx_suf_hex, contract_hash, abi ):
    
    global global_wait_for_confirm
    global_origin_value = global_wait_for_confirm 
    length = len(tx_suf_hex) // 2
    #length -= 6400 # already uploaded
    if( (length % 3200) > 0 ):
        raise "Invalid length"
    num_iters = length // 3200
    for i in range(num_iters):
        print "debug_extendCoinbaseTxOutput"
        #global_wait_for_confirm = ((i % 3 ) == 0)
        print call_function( key, 0, contract_hash, abi, "debug_extendCoinbaseTxOutput", [0,3200] )
        print "(" + str(i) + "/" + str(num_iters) + ")"
    global_wait_for_confirm = global_origin_value
        
    print "register"
    print call_function( key, 0, contract_hash, abi, "register", [0xdeadbeef] )


def prepare_contract_env( num_shares, aug_merkle, contract_hash, abi ):
    print "submitShares"    
    print call_function( key, 0, contract_hash, abi, "submitShares", [aug_merkle,num_shares] )         
         

################################################################################

def submit_full_block( coinbase_prefix, merkle_branch, sibil, blockHeader, timestampindex ):
    params = [coinbase_prefix, merkle_branch, sibil, blockHeader]
    prev_block = blockHeader
    for index in range(1,6):
        header_hex = "ff" * 4 + b2h(encoding.double_sha256(prev_block)) + (40 * "ff")
        nonce = 0
        while(True):
            nonce_hex = ("%0.4x" % nonce).zfill(8)
            result_header_hex = header_hex + nonce_hex
            sha = int(b2h(encoding.double_sha256(h2b(result_header_hex))),16)
            if( sha & 0x03 == 0 ):
                header_hex = result_header_hex 
                break
            nonce += 1
        header = h2b(header_hex)
        params.append(header)
        prev_block = header
    
    print "submitFullBlock"
    params.append(timestampindex)
    call_function( key, 0, contract_hash, abi, "submitFullBlock", params )    
            
################################################################################            
        
def payment_request():
    print "requestPayment"
    print call_function( key, 0, contract_hash, abi, "requestPayment", [0,2] )
    print "constructCoinbaseTx"        
    print call_function( key, 0, contract_hash, abi, "constructCoinbaseTx", [2] )    


################################################################################


p2pool_block_header = "abcdef1234567800" * 10
p2pool_coinbase_tx_start = "aa" * 64
p2pool_coinbase_tx_end = "cc" * 32 * 300

global_wait_for_confirm = False

key = utils.sha3("Smart Pool2")
address = b2h( utils.privtoaddr(key) )


global_wait_for_confirm = True
#( contract_data, abi ) = get_contract_data( "./DumbPool", [])#,24,5,2016] )


#print address
#global_wait_for_confirm = True
#( contract_data, abi ) = get_contract_data( "./SmartPool", [])#,24,5,2016] )

#( contract_data, abi ) = get_contract_data( "../buttcoin/BetOnHardFork", [])#,24,5,2016] )

contract_hash = None
(str, contract_hash) = upload_contract( key, contract_data, 0 )
xsd

contract_hash = "e04c87f878735d065b9d4b1535f8be73830d97d5"


# smart
#https://testnet.etherscan.io/address/0xa8f5d65904026fd71de5da06a466afce42010e0b
# dumb
#https://testnet.etherscan.io/address/0xe04c87f878735d065b9d4b1535f8be73830d97d5
#use_ether_scan = True
first = True
aug_tree_height = 10
for i in range(5):
    if first:
        prepare_first_run( p2pool_coinbase_tx_end, contract_hash, abi )
        first = False

    print "Reset"
    print call_function( key, 0, contract_hash, abi, "debug_resetuser", [] )

    print str(aug_tree_height)
    
    params = generate_verification_params( aug_tree_height, 10, p2pool_coinbase_tx_start, p2pool_coinbase_tx_end)
    aug_merkle = (params[0])[0]
    
    
    prepare_contract_env( 2 ** aug_tree_height, aug_merkle, contract_hash, abi)
    
    global_wait_for_confirm = True
    use_ether_scan = False
    
    #print call_function( key, 0, contract_hash, abi, "verifyShare", [params[6], params[3], params[4], params[5], params[7]] )
    
    print "verify"
    print call_function( key, 0, contract_hash, abi, "verifyPendingShares", params )
    submit_full_block(params[6], params[3], params[4], params[5], params[7])
    #payment_request()
    
    aug_tree_height = aug_tree_height + 10
