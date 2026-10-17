// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {IKimlik} from "../src/IKimlik.sol";
import {Kaydol} from "../script/Kaydol.s.sol";

/// M1 kabul testleri. Fuji çatallanır; kayıt yerelde denenir, gaz harcanmaz.
/// Gerçek kayıt sonrası: PROOF1_AGENT_ID ve PROOF1_FUJI_ADDRESS ortamda olunca son test zinciri okur.
contract KayitTest is Test {
    IKimlik constant KIMLIK = IKimlik(0x8004A818BFB912233c491871b3d84c89A494BD9e);
    Kaydol kaydol;

    function setUp() public {
        vm.createSelectFork("fuji");
        kaydol = new Kaydol();
    }

    function test_FujiKimlikSurumu() public view {
        assertEq(block.chainid, 43113);
        assertEq(KIMLIK.getVersion(), "2.0.0");
    }

    function test_KayitDosyasiAlanlari() public view {
        string memory json = kaydol.kayitJson();
        assertEq(vm.parseJsonString(json, ".type"), "https://eips.ethereum.org/EIPS/eip-8004#registration-v1");
        assertEq(vm.parseJsonString(json, ".name"), "proof1");
        assertTrue(vm.parseJsonBool(json, ".active"));
        assertTrue(vm.parseJsonBool(json, ".x402Support") == false);
        string memory gorsel = vm.parseJsonString(json, ".image");
        assertTrue(vm.indexOf(gorsel, "data:image/svg+xml;base64,") == 0, "gorsel gomulu olmali");
    }

    function test_AgentURIGomuluVeKucuk() public view {
        string memory uri = kaydol.agentURI();
        assertTrue(vm.indexOf(uri, "data:application/json;base64,") == 0);
        assertEq(uri, string.concat("data:application/json;base64,", vm.toBase64(bytes(kaydol.kayitJson()))));
        // Zincire yazıldığı için küçük kalmalı (gaz).
        assertLt(bytes(uri).length, 3000);
    }

    function test_KayitSimulasyonu() public {
        string memory uri = kaydol.agentURI();
        address proof1 = makeAddr("proof1");

        vm.recordLogs();
        vm.prank(proof1);
        uint256 agentId = KIMLIK.register(uri);

        assertEq(KIMLIK.ownerOf(agentId), proof1);
        assertEq(KIMLIK.tokenURI(agentId), uri);
        assertEq(KIMLIK.getMetadata(agentId, "agentWallet"), abi.encodePacked(proof1));

        bytes32 konu = keccak256("Registered(uint256,string,address)");
        bool goruldu;
        Vm.Log[] memory kayitlar = vm.getRecordedLogs();
        for (uint256 i; i < kayitlar.length; i++) {
            if (kayitlar[i].emitter == address(KIMLIK) && kayitlar[i].topics[0] == konu) {
                assertEq(uint256(kayitlar[i].topics[1]), agentId);
                assertEq(address(uint160(uint256(kayitlar[i].topics[2]))), proof1);
                goruldu = true;
            }
        }
        assertTrue(goruldu, "Registered olayi yok");
    }

    function test_MuhurMetaVerisi() public {
        uint256 agentId = vm.envOr("PROOF1_AGENT_ID", uint256(0));
        address muhur = vm.envOr("PROOF1_SEAL_ADDRESS", address(0));
        if (agentId == 0 || muhur == address(0)) {
            vm.skip(true);
        }
        assertEq(KIMLIK.getMetadata(agentId, "proof1.seal"), abi.encode(muhur));
    }

    function test_ZincirdekiKayitDosyasiGuncel() public {
        uint256 agentId = vm.envOr("PROOF1_AGENT_ID", uint256(0));
        if (agentId == 0) {
            vm.skip(true);
        }
        assertEq(KIMLIK.tokenURI(agentId), kaydol.agentURI(), "zincirdeki kayit dosyasi kayit/ ile ayni olmali");
    }

    function test_KayitDosyasiMuhuruGosteriyor() public view {
        string memory json = kaydol.kayitJson();
        assertEq(vm.parseJsonString(json, ".services[0].name"), "seal");
        assertEq(
            vm.parseJsonString(json, ".services[0].endpoint"),
            string.concat("eip155:43113:", vm.toString(vm.envAddress("PROOF1_SEAL_ADDRESS")))
        );
        assertEq(vm.parseJsonUint(json, ".registrations[0].agentId"), vm.envUint("PROOF1_AGENT_ID"));
    }

    function test_GercekKayit() public {
        uint256 agentId = vm.envOr("PROOF1_AGENT_ID", uint256(0));
        if (agentId == 0) {
            vm.skip(true);
        }
        assertEq(KIMLIK.ownerOf(agentId), vm.envAddress("PROOF1_FUJI_ADDRESS"));
        assertTrue(vm.indexOf(KIMLIK.tokenURI(agentId), "data:application/json;base64,") == 0);
    }
}
