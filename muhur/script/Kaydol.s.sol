// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {IKimlik} from "../src/IKimlik.sol";

/// proof1'ı Avalanche Fuji'deki resmi ERC-8004 Identity sözleşmesine kaydeder.
/// Kayıt dosyası ve görsel zincire data: URI olarak gömülür; barındırma gerekmez.
///   forge script script/Kaydol.s.sol --rpc-url fuji --broadcast
contract Kaydol is Script {
    IKimlik constant KIMLIK = IKimlik(0x8004A818BFB912233c491871b3d84c89A494BD9e);

    function kayitJson() public view returns (string memory) {
        string memory svg = vm.readFile("kayit/gorsel.svg");
        string memory gorsel = string.concat("data:image/svg+xml;base64,", vm.toBase64(bytes(vm.trim(svg))));
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
}
