// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {IKimlik} from "../src/IKimlik.sol";

/// proof1'ı Avalanche Fuji'deki resmi ERC-8004 Identity sözleşmesine kaydeder.
/// Kayıt dosyası ve görsel zincire data: URI olarak gömülür; barındırma gerekmez.
///   forge script script/Kaydol.s.sol --rpc-url fuji --broadcast
/// Kayıt dosyası ya da görsel değişince: forge script script/Kaydol.s.sol --sig "guncelle()" --rpc-url fuji --broadcast
contract Kaydol is Script {
    IKimlik constant KIMLIK = IKimlik(0x8004A818BFB912233c491871b3d84c89A494BD9e);

    function kayitJson() public view returns (string memory) {
        // Komiser Kuş, 256 px JPEG (~15 KB): zincire gömüldüğü için küçük tutulur.
        string memory gorsel = string.concat("data:image/jpeg;base64,", vm.toBase64(vm.readFileBinary("kayit/gorsel.jpg")));
        return vm.replace(vm.trim(vm.readFile("kayit/kayit.json")), "__GORSEL__", gorsel);
    }

    function agentURI() public view returns (string memory) {
        return string.concat("data:application/json;base64,", vm.toBase64(bytes(kayitJson())));
    }

    function run() external returns (uint256 agentId) {
        require(block.chainid == 43113, "yalniz Avalanche Fuji");
        uint256 anahtar = vm.envUint("PROOF1_FUJI_PRIVATE_KEY");
        string memory uri = agentURI();

        vm.startBroadcast(anahtar);
        agentId = KIMLIK.register(uri);
        vm.stopBroadcast();

        console.log("agentId", agentId);
        console.log("sahip", KIMLIK.ownerOf(agentId));
    }

    /// Var olan kimliğin kayıt dosyasını (görsel dahil) kayit/ klasöründekiyle değiştirir; yalnız sahip yapabilir.
    function guncelle() external {
        require(block.chainid == 43113, "yalniz Avalanche Fuji");
        uint256 agentId = vm.envUint("PROOF1_AGENT_ID");
        uint256 anahtar = vm.envUint("PROOF1_FUJI_PRIVATE_KEY");
        require(KIMLIK.ownerOf(agentId) == vm.addr(anahtar), "kimligin sahibi degil");
        string memory uri = agentURI();

        vm.startBroadcast(anahtar);
        KIMLIK.setAgentURI(agentId, uri);
        vm.stopBroadcast();

        require(keccak256(bytes(KIMLIK.tokenURI(agentId))) == keccak256(bytes(uri)), "tokenURI guncellenmedi");
        console.log("agentURI bayt", bytes(uri).length);
    }
}
