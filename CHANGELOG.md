# Changelog

## Version 1.1.0

- New connection type: DonutShop dongle over Wi-Fi (no USB cable to Home Assistant needed)
- Real power state, profile, input and output polled from DonutShop `/api/status` (v0.7.25+)
- Fallback to DonutShop `/cmd` for older DonutShop firmware
- Commands containing a space are sent verbatim (raw RT4K serial commands)
- Delay between commands no longer blocks a Home Assistant worker thread
- French translation
- Existing USB serial entries keep working unchanged

## Version 1.0.0 (January 2026)

### Initial Release
- Full RetroTINK-4K (Pro and CE) serial control
- 70+ commands supported
- Power state tracking
- Automatic serial port configuration
- Device model selection (Pro or CE)
- Multiple device support
- Home Assistant UI-based setup
- Compatible with Unfolded Circle Remote 3
