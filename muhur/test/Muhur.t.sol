// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Proof1Muhur} from "../src/Proof1Muhur.sol";

/// Test için en küçük ERC-721 sahiplik taklidi.
contract SahteKimlik {
    mapping(uint256 => address) public ownerOf;

    function ver(uint256 agentId, address sahip) external {
        ownerOf[agentId] = sahip;
    }
}

/// M2 kabul testleri (yerel): sahiplik, tek yazım, olay, okuma, sıra.
contract MuhurTest is Test {
    event Sealed(uint256 indexed agentId, uint32 indexed day, bytes32 root, bytes32 prevRoot);

    SahteKimlik kimlik;
    Proof1Muhur muhur;
    address proof1 = makeAddr("proof1");
    address yabanci = makeAddr("yabanci");
    uint256 constant AJAN = 263;

    function setUp() public {
        kimlik = new SahteKimlik();
        kimlik.ver(AJAN, proof1);
        muhur = new Proof1Muhur(address(kimlik));
    }

    function test_SahipMuhurler() public {
        vm.prank(proof1);
        muhur.seal(AJAN, 20261017, keccak256("kok-1"));
        assertEq(muhur.rootOf(AJAN, 20261017), keccak256("kok-1"));
    }

    function test_SahipOlmayanReddedilir() public {
        vm.prank(yabanci);
        vm.expectRevert(Proof1Muhur.SahipDegil.selector);
        muhur.seal(AJAN, 20261017, keccak256("kok-1"));
    }

    function test_AyniGunIkinciYazimReddedilir() public {
        vm.startPrank(proof1);
        muhur.seal(AJAN, 20261017, keccak256("kok-1"));
        vm.expectRevert(Proof1Muhur.ZatenMuhurlu.selector);
        muhur.seal(AJAN, 20261017, keccak256("kok-2"));
        vm.stopPrank();
        assertEq(muhur.rootOf(AJAN, 20261017), keccak256("kok-1"));
    }

    function test_BosKokReddedilir() public {
        vm.prank(proof1);
        vm.expectRevert(Proof1Muhur.BosKok.selector);
        muhur.seal(AJAN, 20261017, bytes32(0));
    }

    function test_GecmisGunReddedilir() public {
        vm.startPrank(proof1);
        muhur.seal(AJAN, 20261017, keccak256("kok-1"));
        vm.expectRevert(Proof1Muhur.GeriTarih.selector);
        muhur.seal(AJAN, 20261016, keccak256("kok-0"));
        vm.stopPrank();
    }

    function test_OlayAlanlariVeOncekiKok() public {
        vm.startPrank(proof1);
        vm.expectEmit(true, true, false, true, address(muhur));
        emit Sealed(AJAN, 20261016, keccak256("kok-1"), bytes32(0));
        muhur.seal(AJAN, 20261016, keccak256("kok-1"));

        vm.expectEmit(true, true, false, true, address(muhur));
        emit Sealed(AJAN, 20261017, keccak256("kok-2"), keccak256("kok-1"));
        muhur.seal(AJAN, 20261017, keccak256("kok-2"));
        vm.stopPrank();

        assertEq(muhur.lastDay(AJAN), 20261017);
    }

    function test_MuhurlenmemisGunSifirDoner() public view {
        assertEq(muhur.rootOf(AJAN, 20261017), bytes32(0));
    }
}

/// M2 kabul testi (Fuji çatalı): gerçek ERC-8004 kimliği 263 ile.
contract MuhurFujiTest is Test {
    address constant KIMLIK = 0x8004A818BFB912233c491871b3d84c89A494BD9e;

    function test_GercekKimlikleMuhur() public {
        vm.createSelectFork("fuji");
        uint256 agentId = vm.envOr("PROOF1_AGENT_ID", uint256(0));
        if (agentId == 0) {
            vm.skip(true);
        }
        address sahip = vm.envAddress("PROOF1_FUJI_ADDRESS");
        Proof1Muhur muhur = new Proof1Muhur(KIMLIK);

        vm.prank(makeAddr("yabanci"));
        vm.expectRevert(Proof1Muhur.SahipDegil.selector);
        muhur.seal(agentId, 20261017, keccak256("kok"));

        vm.prank(sahip);
        muhur.seal(agentId, 20261017, keccak256("kok"));
        assertEq(muhur.rootOf(agentId, 20261017), keccak256("kok"));
    }

    function test_DeployEdilmisMuhur() public {
        address adres = vm.envOr("PROOF1_SEAL_ADDRESS", address(0));
        if (adres == address(0)) {
            vm.skip(true);
        }
        vm.createSelectFork("fuji");
        Proof1Muhur muhur = Proof1Muhur(adres);
        assertEq(address(muhur.kimlik()), KIMLIK);
    }
}
