// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {IKimlik} from "../src/IKimlik.sol";
import {Kaydol} from "../script/Kaydol.s.sol";

/// M1 kabul testleri. Fuji çatallanır; kayıt yerelde denenir, gaz harcanmaz.
/// Gerçek kayıt sonrası: PROOF1_AGENT_ID ve PROOF1_FUJI_ADDRESS ortamda olunca son test zinciri okur.
/// Kayıt dosyası ~28 KB: yazma benzetimleri yüzlerce depolama yuvası okur, arşiv olmayan uçta (publicnode) çatal
/// bu okumaları karşılayamaz. Bu iki test yalnız FUJI_ARSIV=true iken koşar; yoksa ön deneme `cast estimate` ile:
///   cast estimate 0x8004…BD9e 'setAgentURI(uint256,string)' 263 "<uri>" --from <sahip> --rpc-url fuji
contract KayitTest is Test {
    IKimlik constant KIMLIK = IKimlik(0x8004A818BFB912233c491871b3d84c89A494BD9e);
    Kaydol kaydol;

    function setUp() public {
        vm.createSelectFork("fuji");
        kaydol = new Kaydol();
    }

    /// tokenURI'yi tek bir düğüm tarafı eth_call ile okur (çatalın yuva yuva okuması arşivsiz uçta düşer).
    function zincirdekiURI(uint256 agentId) internal returns (string memory) {
        string memory params = string.concat(
            '[{"to":"', vm.toString(address(KIMLIK)), '","data":"',
            vm.toString(abi.encodeWithSignature("tokenURI(uint256)", agentId)), '"},"latest"]'
        );
        return abi.decode(vm.rpc("eth_call", params), (string));
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
        assertTrue(vm.indexOf(gorsel, "data:image/jpeg;base64,") == 0, "gorsel gomulu olmali");
    }

    function test_AgentURIGomuluVeKucuk() public view {
        string memory uri = kaydol.agentURI();
        assertTrue(vm.indexOf(uri, "data:application/json;base64,") == 0);
        assertEq(uri, string.concat("data:application/json;base64,", vm.toBase64(bytes(kaydol.kayitJson()))));
        // Zincire yazıldığı için küçük kalmalı (gaz): görsel ~15 KB, kayıt dosyası iki kez base64.
        assertLt(bytes(uri).length, 32_000);
    }

    function test_KayitSimulasyonu() public {
        if (!vm.envOr("FUJI_ARSIV", false)) {
            vm.skip(true);
        }
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

    function test_GorselGuncellemeSimulasyonu() public {
        uint256 agentId = vm.envOr("PROOF1_AGENT_ID", uint256(0));
        if (agentId == 0 || !vm.envOr("FUJI_ARSIV", false)) {
            vm.skip(true);
        }
        string memory uri = kaydol.agentURI();
        vm.prank(KIMLIK.ownerOf(agentId));
        uint256 once = gasleft();
        KIMLIK.setAgentURI(agentId, uri);
        uint256 harcanan = once - gasleft();
        emit log_named_uint("setAgentURI gaz", harcanan);
        assertEq(KIMLIK.tokenURI(agentId), uri);
        assertLt(harcanan, 25_000_000, "Fuji blok siniri 32M; pay birakilmali");

        vm.prank(makeAddr("yabanci"));
        vm.expectRevert();
        KIMLIK.setAgentURI(agentId, "data:,x");
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
        assertEq(zincirdekiURI(agentId), kaydol.agentURI(), "zincirdeki kayit dosyasi kayit/ ile ayni olmali");
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
        assertTrue(vm.indexOf(zincirdekiURI(agentId), "data:application/json;base64,") == 0);
    }
}
