#!/usr/bin/env python2
# Copyright (c) 2016 The Bitcoin developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

#
# Test MVF post fork retargeting
#
# on node 0, test pure block height trigger at height FORK_BLOCK
#

from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import *
from test_framework.arith import *
from random import randint

# period (in blocks) from fork activation until retargeting returns to normal
# MVF-BU TODO: Revert to 180*144
HARDFORK_RETARGET_BLOCKS = 90*144    # the period when retargeting returns to original
FORK_BLOCK = 2020                    # needs to be >= 2018 to test fork difficulty reset
POW_LIMIT = 0x207fffff
PREFORK_BLOCKTIME = 1                # before the fork during the regtest
ORIGINAL_DIFFADJINTERVAL = 2016      # the original difficulty adjustment interval
STANDARD_BLOCKTIME = 600             # the standard target seconds for a block

def CalculateMVFNextWorkRequired(bits, actualBlockTimeSecs, targetBlockInterval):
    # Returns difficulty using the fork reset formula in pow.cpp:CalculateMVFNextWorkRequired()

    bnPowLimit = bits2target_int(hex2bin(int2hex(POW_LIMIT))) # MVF-BU moved here

    # Limit adjustment step
    nActualTimespan = actualBlockTimeSecs

    # Target by interval
    nTargetTimespan = targetBlockInterval * STANDARD_BLOCKTIME

    # permit abrupt changes for a few blocks after the fork i.e. when nTargetTimespan is < 30 minutes (MVHF-BU-DES-DIAD-5)
    if (nTargetTimespan >= STANDARD_BLOCKTIME * 3) :
        # prevent abrupt changes to target
        if (nActualTimespan < nTargetTimespan/4) :
            nActualTimespan = nTargetTimespan/4
        if (nActualTimespan > nTargetTimespan*4) :
            nActualTimespan = nTargetTimespan*4

    # compare with debug.log
    #print "nTargetTimespan=%d nActualTimespan=%d" % (nTargetTimespan,nActualTimespan)

    # Retarget
    bnOld = bits2target_int(hex2bin(bits))     # SetCompact
    # MVF-BU begin: move division before multiplication
    # at regtest difficulty, the multiplication is prone to overflowing
    bnNew1 = bnOld / nTargetTimespan
    bnNew2 = bnNew1 * nActualTimespan

    # Test for overflow
    if (bnNew2 / nActualTimespan != bnNew1 or bnNew2 > bnPowLimit):
        bnNew = bnPowLimit
    else :
        bnNew = bnNew2

    newBits = "0x%s" % bin2hex(target_int2bits(bnNew)) # GetCompact
    nBitsReset = int(newBits,0)
    return nBitsReset


def CalculateMVFResetWorkRequired(bits):
    # Returns difficulty using the fork reset formula in pow.cpp:CalculateMVFResetWorkRequired()

    bnPowLimit = bits2target_int(hex2bin(int2hex(POW_LIMIT)))
    # drop difficulty via factor
    nDropFactor = 4
    # total blocktimes prefork during run_test
    nActualTimespan = ORIGINAL_DIFFADJINTERVAL * PREFORK_BLOCKTIME
    # used reduced target time span while within the re-target period
    nTargetTimespan = nActualTimespan / nDropFactor

    # compare with debug.log
    #print "nTargetTimespan=%d nActualTimespan=%d" % (nTargetTimespan,nActualTimespan)

    bnOld = bits2target_int(hex2bin(bits))     # SetCompact
    bnNew1 = bnOld / nTargetTimespan
    bnNew2 = bnNew1 * nActualTimespan

    # check for overflow or overlimit
    if (bnNew2 / nActualTimespan != bnNew1 or bnNew2 > bnPowLimit):
        bnNew = bnPowLimit
    else:
        bnNew = bnNew2

    nBitsReset = int("0x%s" % bin2hex(target_int2bits(bnNew)),0) # GetCompact
    return nBitsReset

# formula debug testing
# useful for testing whenever the reset formula changes pow.cpp:CalcForkResetTarget()
##bits = "1d00ffff" # 1.000000000
##bits = "201fffff" # 0.0000000019
##bits = "203ffff6" # 0.0000000009
##bits = "1f03f355" # 0.0000038624
#bits = "1e132d35"  # 1e19919b 0.0001527719
#print "before: 0x%s = %.10f" % (bits,bits2difficulty(int("0x%s"%bits,0)))

##reset = CalculateMVFResetWorkRequired(bits)
#reset = CalculateMVFNextWorkRequired(bits,800,1)
#diff = bits2difficulty(reset)
#print "after : 0x%s = %.10f" % (int2hex(reset),diff)
#raw_input()
#assert_equal(0,1)
# end debug testing

class MVF_RETARGET_Test(BitcoinTestFramework):

    def setup_chain(self):
        print("Initializing test directory " + self.options.tmpdir)
        initialize_chain_clean(self.options.tmpdir, 1)

    def setup_network(self):
        self.nodes = []
        self.is_network_split = False
        self.nodes.append(start_node(0, self.options.tmpdir
            ,["-forkheight=%s"%FORK_BLOCK, "-force-retarget","-rpcthreads=100","-blockversion=%s" % "0x20000000" ]
            ))

    def is_fork_triggered_on_node(self, node=0):
        """ check in log file if fork has triggered and return true/false """
        # MVF-BU TODO: extend to check using RPC info about forks
        nodelog = self.options.tmpdir + "/node%s/regtest/debug.log" % node
        hf_active = search_file(nodelog, "isMVFHardForkActive=1")
        fork_actions_performed = search_file(nodelog, "MVF: performing fork activation actions")
        return (len(hf_active) > 0 and len(fork_actions_performed) == 1)

    def run_test(self):
        # check that fork does not trigger before the forkheight
        print "Generating %s pre-fork blocks" % (FORK_BLOCK - 1)
        #block0 already exists
        for n in range(FORK_BLOCK - 1):
            # Change block times so that difficulty develops
            best_block = self.nodes[0].getblock(self.nodes[0].getbestblockhash(), True)
            self.nodes[0].setmocktime(best_block['time'] + PREFORK_BLOCKTIME)
            self.nodes[0].generate(1)

        # Read difficulty before the fork
        best_block = self.nodes[0].getblock(self.nodes[0].getbestblockhash(), True)
        print "Pre-fork difficulty: %.10f %s " % (best_block['difficulty'], best_block['bits'])
        nBits = CalculateMVFResetWorkRequired(best_block['bits'])
        reset_bits = int2hex(nBits)
        reset_diff_expected = bits2difficulty(nBits)
        assert_greater_than(reset_diff_expected, 0)

        # Test fork did not trigger prematurely
        assert_equal(False, self.is_fork_triggered_on_node(0))
        print "Fork did not trigger prematurely"

        # Generate fork block
        best_block = self.nodes[0].getblock(self.nodes[0].getbestblockhash(), True)
        self.nodes[0].setmocktime(best_block['time'] + STANDARD_BLOCKTIME)
        self.nodes[0].generate(1)
        assert_equal(True,   self.is_fork_triggered_on_node(0))

        best_block = self.nodes[0].getblock(self.nodes[0].getbestblockhash(), True)
        print "Fork triggered successfully (block height %s)" % best_block['height']

        # Test fork difficulty reset
        #print "expected = %.10f actual = %.10f" % (reset_diff_expected,best_block['difficulty'])
        assert_equal(best_block['bits'],reset_bits)
        #assert_equal(best_block['bits'], "207eeeee") # fixed reset
        print "Post-fork difficulty reset success: %.10f %s " % (best_block['difficulty'], best_block['bits'])

        # use to track how many times the same bits are used in a row
        prev_block = 0
        diffadjinterval = 0
        # the first nexttimeblock test phase is cyclical increases of 50 seconds starting from here
        # if the starting number is too low it may cause timeout errors too often
        next_block_time = 300
        count_bits_used = 0

        # print column titles
        print "nBits changed @ Time,Block,Delta(secs),nBits,Used,DiffInterval,Difficulty,NextBits"

        # start generating MVF blocks with varying time stamps
        oneRetargetBlockAfterMVFRetargetPeriod = HARDFORK_RETARGET_BLOCKS+ORIGINAL_DIFFADJINTERVAL+1
        for n in xrange(oneRetargetBlockAfterMVFRetargetPeriod):
            best_block = self.nodes[0].getblock(self.nodes[0].getbestblockhash(), True)
            prev_block = self.nodes[0].getblock(best_block['previousblockhash'], True)

            # track bits used
            if prev_block['bits'] == best_block['bits'] or best_block['height'] == FORK_BLOCK:
                count_bits_used += 1
            else:
                # when the bits change then output the retargeting metrics
                # for the previous group of bits
                first_block = self.nodes[0].getblock(self.nodes[0].getblockhash(prev_block['height'] - diffadjinterval))
                actualBlockTimeSecs = prev_block['time'] - first_block['time']
                avgBlockTimeSecs = actualBlockTimeSecs / count_bits_used

                if n > HARDFORK_RETARGET_BLOCKS :
                    # returns to standard targetting
                    nextBits = "standard"
                    #best_diff_expected = ""
                    nBits = 0
                else:
                    # during MVF retarget period test retarget difficulty function
                    nBits = CalculateMVFNextWorkRequired(prev_block['bits'], actualBlockTimeSecs, diffadjinterval)
                    nextBits = int2hex(nBits)
                    #best_diff_expected = bits2difficulty(nBits)
                    #print "%s %.10f" % (int2hex(nextBits), best_diff_expected)

                    # Test difficulty
                    assert_equal(best_block['bits'], nextBits)

                print "%s,%d,%d,%s,%d,%d,%.10f,%s " %(
                    time.strftime("%Y-%m-%d %H:%M",time.gmtime(prev_block['time'])),
                    prev_block['height'],
                    avgBlockTimeSecs,
                    prev_block['bits'],
                    count_bits_used,
                    diffadjinterval,
                    prev_block['difficulty'],
                    nextBits
                    )

                # reset bits tracking variables
                count_bits_used = 1
                #raw_input()
            #### end if prev_block['bits'] == best_block['bits']

            # Test processed bits are used within the expected difficulty interval
            # except when the bits is at the bits limit: 207fffff
            diffadjinterval = self.nodes[0].getblockchaininfo()['difficultyadjinterval']

            if int("0x%s"%prev_block['bits'],0) <> POW_LIMIT :
                assert_less_than_equal(count_bits_used, diffadjinterval)

            # Setup various block time interval tests
            if n in range(0,11) :
                next_block_time = next_block_time + 50
            elif n in range(11,18) :
                next_block_time = 300
            elif n in range(18,26) :
                next_block_time = 1200
            elif n in range(26,500) :
                next_block_time = 600
            elif n in range(500,2000) :
                # simulate slow blocks
                # this will cause bits to hit the limit POW_LIMIT
                next_block_time = randint(1000,3000)
            elif n in range(2000,2500) :
                # simulate faster blocks
                # this will cause bits to hit the limit POW_LIMIT
                next_block_time = randint(100,300)
            else:
                # simulate ontime blocks i.e. hash power/difficult around 600 secs
                next_block_time = randint(500,700)

            self.nodes[0].setmocktime(best_block['time'] + next_block_time)

            # Test the interval matches the interval defined in params.MVFPowTargetTimespan()
            if n in range(0,11) :
                diff_interval_expected = 1     # 10 mins
            elif n in range(11,44) :
                diff_interval_expected = 3     # 30 mins
            elif n in range(44,102) :
                diff_interval_expected = 6     # 1 hour
            elif n in range(102,2012) :
                diff_interval_expected = 18    # 3 hours
            elif n in range(2012,HARDFORK_RETARGET_BLOCKS) :
                diff_interval_expected = 72    # 12 hours
            else:
                diff_interval_expected = ORIGINAL_DIFFADJINTERVAL  # 14 days original

            assert_equal(diff_interval_expected, diffadjinterval)

            # print info for every block
            #print "%s :: %s :: %d :: %s :: %d" %(
                #best_block['height'],
                #time.strftime("%H:%M",time.gmtime(best_block['time'])),
                #best_block['bits'],
                #count_bits_used)

            # generate the next block
            self.nodes[0].generate(1)

        #### end for n in xrange

        print "Done."
        #raw_input() # uncomment here to pause shutdown and check the logs

if __name__ == '__main__':
    MVF_RETARGET_Test().main()
