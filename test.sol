contract test {
	uint[100] balance;


	function test() {
		for( uint index = 0 ; index < 100 ; index++ ) balance[index] = 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff;
	}
	function check( bytes input ) returns(bytes32) {
		return sha256(sha256(input));
	}

	function check( uint[] input) returns(bool) {
		for( uint index = 0 ; index < input.length ; index++ ) {
			if( input[index] != balance[index % 100] ) return false;
		}
		return true;
	}

	
}
