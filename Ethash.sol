pragma solidity ^0.4.8;

import "./SHA3_512.sol";


contract Ethash {
    
    function halfsha3( bytes32 input ) constant returns(uint[2]) {
        uint result = uint(sha3(input));
        uint secondHalf = result / (2**128);
        uint firstHalf = result & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF;
        
        return [firstHalf,secondHalf];
    }
    
    function shanumbers(uint x, uint y) constant returns(uint) {
        return uint(sha3(x,y));
    }
    
    SHA3_512 sha3_512;
    function Ethash() {
        sha3_512 = new SHA3_512();
    }
    uint merkleRoot = 0xe5f2eaabb3843d3d8cd9aeab4b8d6db4cda2714d5ead67f1d0d8835cf6995780;
    
    function setMerkleRoot(uint root) {
        merkleRoot = root;
    }
     
    function fnv( uint v1, uint v2 ) constant returns(uint) {
        return ((v1*0x01000193) ^ v2) & 0xFFFFFFFF;
    }



    function computeCacheRoot( uint index,
                               uint indexInElementsArray,
                               uint[] elements,
                               uint[] witness,
                               uint branchSize ) constant returns(uint) {
 
                                            
        uint leaf = computeLeaf(elements, indexInElementsArray) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF;

        uint left;
        uint right;
        
        branchSize /= 2;
        uint witnessIndex = indexInElementsArray * branchSize;

        for( uint depth = 0 ; depth < branchSize ; depth++ ) {
            uint node  = witness[witnessIndex + depth] & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF;
            if( index & 0x1 == 0 ) {
                left = leaf;
                right = node;
            }
            else {
                left = node;
                right = leaf;
            }
            
            leaf = uint(sha3(left,right)) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF;
            index = index / 2;

            node  = witness[witnessIndex + depth] / (2**128);
            if( index & 0x1 == 0 ) {
                left = leaf;
                right = node;
            }
            else {
                left = node;
                right = leaf;
            }
            
            leaf = uint(sha3(left,right)) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF;
            index = index / 2;
            
        }
        
        
        return leaf;
    }

    
    function toBE( uint x ) constant returns(uint) {
        uint y = 0;
        for( uint i = 0 ; i < 32 ; i++ ) {
            y = y * 256;
            y += (x & 0xFF);
            x = x / 256;            
        }
        
        return y;
        
    }
    
    function computeSha3( uint[16] s, uint[8] cmix ) constant returns(uint) {
        uint s0 = s[0] + s[1] * (2**32) + s[2] * (2**64) + s[3] * (2**96) +
                  (s[4] + s[5] * (2**32) + s[6] * (2**64) + s[7] * (2**96))*(2**128);

        uint s1 = s[8] + s[9] * (2**32) + s[10] * (2**64) + s[11] * (2**96) +
                  (s[12] + s[13] * (2**32) + s[14] * (2**64) + s[15] * (2**96))*(2**128);
                  
        uint c = cmix[0] + cmix[1] * (2**32) + cmix[2] * (2**64) + cmix[3] * (2**96) +
                  (cmix[4] + cmix[5] * (2**32) + cmix[6] * (2**64) + cmix[7] * (2**96))*(2**128);

        
        /* god knows why need to convert to big endian */
        return uint( sha3(toBE(s0),toBE(s1),toBE(c)) );
    }
 
 
    function computeLeaf( uint[] dataSetLookup, uint index ) constant returns(uint) {
        return uint( sha3(dataSetLookup[4*index],
                          dataSetLookup[4*index + 1],
                          dataSetLookup[4*index + 2],
                          dataSetLookup[4*index + 3]) );
                                    
    }
 
    function computeS( uint header, uint nonceLe ) constant returns(uint[16]) {
        uint[9]  memory M;
        
        
        M[0] = uint(header) & 0xFFFFFFFFFFFFFFFF;
        header = header / 2**64;
        M[1] = uint(header) & 0xFFFFFFFFFFFFFFFF;
        header = header / 2**64;
        M[2] = uint(header) & 0xFFFFFFFFFFFFFFFF;
        header = header / 2**64;
        M[3] = uint(header) & 0xFFFFFFFFFFFFFFFF;

        M[4] = nonceLe;
        
        return sha3_512.sponge(M);
    }
    event Log( uint result );
    function hashimoto( bytes32 header,
                        bytes8 nonceLe,
                        uint fullSizeIn128Resultion,
                        uint[] dataSetLookup,
                        uint[] witnessForLookup,
                        uint   branchSize ) constant returns(uint) {
         
        uint[16] memory s;
        uint[32] memory mix;
        uint[8]  memory cmix;
                
        uint i;
        uint j;
        s = computeS(uint(header), uint(nonceLe));
        for( i = 0 ; i < 16 ; i++ ) {
            mix[i] = s[i];
            mix[i+16] = s[i];
        }
                
        uint root = merkleRoot;
        
        for( i = 0 ; i < 64 ; i++ ) {
            uint p = fnv( i ^ s[0], mix[i % 32]) % fullSizeIn128Resultion;
            
            if( computeCacheRoot( p, i, dataSetLookup,  witnessForLookup, branchSize )  != root ) {
                // PoW failed
                return 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF;
            }           

            for( j = 0 ; j < 8 ; j++ ) {
                mix[j] = fnv(mix[j], dataSetLookup[4*i] & 0xFFFFFFFF );
                mix[j+8] = fnv(mix[j+8], dataSetLookup[4*i + 1] & 0xFFFFFFFF );
                mix[j+16] = fnv(mix[j+16], dataSetLookup[4*i + 2] & 0xFFFFFFFF );                
                mix[j+24] = fnv(mix[j+24], dataSetLookup[4*i + 3] & 0xFFFFFFFF );
                
                dataSetLookup[4*i    ] = dataSetLookup[4*i    ]/(2**32);
                dataSetLookup[4*i + 1] = dataSetLookup[4*i + 1]/(2**32);
                dataSetLookup[4*i + 2] = dataSetLookup[4*i + 2]/(2**32);
                dataSetLookup[4*i + 3] = dataSetLookup[4*i + 3]/(2**32);                
            }
        }
        
        
        for( i = 0 ; i < 32 ; i += 4) {
            cmix[i/4] = (fnv(fnv(fnv(mix[i], mix[i+1]), mix[i+2]), mix[i+3]));
        }
        

        uint result = computeSha3(s,cmix); 
        Log(result);
        return result;
        
    }
}