// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// ERC-8004 Identity Registry (v2.0.0) — proof1'ın kullandığı işlevler.
/// Kaynak: github.com/erc-8004/erc-8004-contracts, abis/IdentityRegistry.json
interface IKimlik {
    event Registered(uint256 indexed agentId, string agentURI, address indexed owner);

    function register(string calldata agentURI) external returns (uint256 agentId);
    function setAgentURI(uint256 agentId, string calldata newURI) external;
    function setMetadata(uint256 agentId, string calldata metadataKey, bytes calldata metadataValue) external;
    function getMetadata(uint256 agentId, string calldata metadataKey) external view returns (bytes memory);
    function ownerOf(uint256 tokenId) external view returns (address);
    function tokenURI(uint256 tokenId) external view returns (string memory);
    function getVersion() external pure returns (string memory);
}
