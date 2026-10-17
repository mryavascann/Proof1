// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface ISahiplik {
    function ownerOf(uint256 tokenId) external view returns (address);
}

/// proof1'ın günlük defter mührü. Her gün için tek bir kök yazılır, üzerine yazılamaz.
/// Mühür defterin o gün var olduğunu ve sonradan değişmediğini kanıtlar; doğruluğunu kanıtlamaz.
/// Zincire adres ya da tutar yazılmaz; yalnız kök.
contract Proof1Muhur {
    ISahiplik public immutable kimlik;

    /// agentId => gün (YYYYMMDD, Europe/Istanbul) => kök
    mapping(uint256 => mapping(uint32 => bytes32)) public rootOf;
    /// agentId => en son mühürlenen gün
    mapping(uint256 => uint32) public lastDay;

    event Sealed(uint256 indexed agentId, uint32 indexed day, bytes32 root, bytes32 prevRoot);

    error SahipDegil();
    error ZatenMuhurlu();
    error BosKok();
    error GeriTarih();

    constructor(address kimlik_) {
        kimlik = ISahiplik(kimlik_);
    }

    function seal(uint256 agentId, uint32 day, bytes32 root) external {
        if (kimlik.ownerOf(agentId) != msg.sender) revert SahipDegil();
        if (root == bytes32(0)) revert BosKok();
        if (rootOf[agentId][day] != bytes32(0)) revert ZatenMuhurlu();
        uint32 onceki = lastDay[agentId];
        if (day < onceki) revert GeriTarih();

        bytes32 prevRoot = rootOf[agentId][onceki];
        rootOf[agentId][day] = root;
        lastDay[agentId] = day;
        emit Sealed(agentId, day, root, prevRoot);
    }
}
