# FightingGame
a fighting game

## Setup

1. Install [Unity Hub](https://unity.com/download) and the Unity editor **6000.3.27f2** (Unity 6.3 LTS).
   Everyone on the project should use this exact version.
2. Install [Git LFS](https://git-lfs.com/) and run `git lfs install` once. Art, models and audio are stored with LFS.
3. Clone the repo, then in Unity Hub choose **Add → Add project from disk** and select the repo folder.

The project uses the Universal Render Pipeline (URP) and the Input System package.

## Online versus (two devices)

Use the same Windows build on both computers. In the Fight scene's ONLINE VERSUS panel:

1. Player one chooses **Host Game**, then copies the join code.
2. Player two enters that code and chooses **Join Code**.
3. The match starts when the second player connects. Host controls VOLT; guest controls EMBER.
4. Both players use A/D to move, W/Space to jump, S to block, J/K/L to attack (or a controller).
5. The host can press R to restart. **Leave room** ends the connection and returns to local CPU play.

The project is linked to the FightingGame Unity Cloud project in khatrin2018. Multiplayer Services 2.4.1 and Netcode for GameObjects 2.7.0 use encrypted Relay connections, anonymous player authentication, and a maximum of two players. No router port forwarding is needed. Relay service usage is subject to the organization's Unity service quotas and pricing.

The host simulates combat. The guest sends buffered inputs; the host sends fighter poses, health, meter, projectiles, timer and round state at 30 Hz. This first version does not implement rollback/prediction or host migration: the guest feels network latency, and losing the host ends the match. A new room creates a new code. Offline CPU/local modes remain available.

### Validation

Build with **Fighting Game > Build Windows (dev)**. Test with two copies on separate devices and networks, including invalid codes, a third player attempting to join, host departure, guest departure, and rehosting. Same-machine testing verifies Relay connectivity but does not replace a real two-network latency test.

Development builds also accept `-network-smoke -host-code-file <path> -network-report <path>` for an automated host, or `-network-smoke -join-code <code> -network-report <path>` for a guest that walks toward the host and attacks. These tests exit after 40 seconds and write match state to the requested report path. Do not use the same report file for both processes.
