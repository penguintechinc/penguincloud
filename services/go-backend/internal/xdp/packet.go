// Package xdp provides packet processing utilities.
package xdp

import (
	"encoding/binary"
	"net"
)

// EtherType constants
const (
	EtherTypeIPv4 = 0x0800
	EtherTypeIPv6 = 0x86DD
	EtherTypeARP  = 0x0806
	EtherTypeVLAN = 0x8100
)

// IP Protocol constants
const (
	IPProtoICMP = 1
	IPProtoTCP  = 6
	IPProtoUDP  = 17
)

// Header sizes
const (
	EthernetHeaderSize = 14
	IPv4MinHeaderSize  = 20
	IPv6HeaderSize     = 40
	TCPMinHeaderSize   = 20
	UDPHeaderSize      = 8
)

// EthernetHeader represents an Ethernet frame header.
type EthernetHeader struct {
	DstMAC    net.HardwareAddr
	SrcMAC    net.HardwareAddr
	EtherType uint16
}

// ParseEthernetHeader parses an Ethernet header from a byte slice.
func ParseEthernetHeader(data []byte) (*EthernetHeader, error) {
	if len(data) < EthernetHeaderSize {
		return nil, ErrPacketTooShort
	}

	return &EthernetHeader{
		DstMAC:    net.HardwareAddr(data[0:6]),
		SrcMAC:    net.HardwareAddr(data[6:12]),
		EtherType: binary.BigEndian.Uint16(data[12:14]),
	}, nil
}

// Serialize writes the Ethernet header to a byte slice.
func (h *EthernetHeader) Serialize(data []byte) error {
	if len(data) < EthernetHeaderSize {
		return ErrBufferTooSmall
	}

	copy(data[0:6], h.DstMAC)
	copy(data[6:12], h.SrcMAC)
	binary.BigEndian.PutUint16(data[12:14], h.EtherType)

	return nil
}

// IPv4Header represents an IPv4 packet header.
type IPv4Header struct {
	Version    uint8
	IHL        uint8 // Header length in 32-bit words
	TOS        uint8
	TotalLen   uint16
	ID         uint16
	Flags      uint8
	FragOffset uint16
	TTL        uint8
	Protocol   uint8
	Checksum   uint16
	SrcIP      net.IP
	DstIP      net.IP
}

// ParseIPv4Header parses an IPv4 header from a byte slice.
func ParseIPv4Header(data []byte) (*IPv4Header, error) {
	if len(data) < IPv4MinHeaderSize {
		return nil, ErrPacketTooShort
	}

	versionIHL := data[0]
	version := versionIHL >> 4
	ihl := versionIHL & 0x0F

	if version != 4 {
		return nil, ErrInvalidPacket
	}

	headerLen := int(ihl) * 4
	if len(data) < headerLen {
		return nil, ErrPacketTooShort
	}

	flagsFrag := binary.BigEndian.Uint16(data[6:8])

	return &IPv4Header{
		Version:    version,
		IHL:        ihl,
		TOS:        data[1],
		TotalLen:   binary.BigEndian.Uint16(data[2:4]),
		ID:         binary.BigEndian.Uint16(data[4:6]),
		Flags:      uint8(flagsFrag >> 13),
		FragOffset: flagsFrag & 0x1FFF,
		TTL:        data[8],
		Protocol:   data[9],
		Checksum:   binary.BigEndian.Uint16(data[10:12]),
		SrcIP:      net.IP(data[12:16]),
		DstIP:      net.IP(data[16:20]),
	}, nil
}

// HeaderLength returns the header length in bytes.
func (h *IPv4Header) HeaderLength() int {
	return int(h.IHL) * 4
}

// Serialize writes the IPv4 header to a byte slice.
func (h *IPv4Header) Serialize(data []byte) error {
	headerLen := h.HeaderLength()
	if len(data) < headerLen {
		return ErrBufferTooSmall
	}

	data[0] = (h.Version << 4) | h.IHL
	data[1] = h.TOS
	binary.BigEndian.PutUint16(data[2:4], h.TotalLen)
	binary.BigEndian.PutUint16(data[4:6], h.ID)
	flagsFrag := (uint16(h.Flags) << 13) | h.FragOffset
	binary.BigEndian.PutUint16(data[6:8], flagsFrag)
	data[8] = h.TTL
	data[9] = h.Protocol
	binary.BigEndian.PutUint16(data[10:12], 0) // Checksum placeholder
	copy(data[12:16], h.SrcIP.To4())
	copy(data[16:20], h.DstIP.To4())

	// Calculate and set checksum
	h.Checksum = calculateIPChecksum(data[:headerLen])
	binary.BigEndian.PutUint16(data[10:12], h.Checksum)

	return nil
}

// UDPHeader represents a UDP packet header.
type UDPHeader struct {
	SrcPort  uint16
	DstPort  uint16
	Length   uint16
	Checksum uint16
}

// ParseUDPHeader parses a UDP header from a byte slice.
func ParseUDPHeader(data []byte) (*UDPHeader, error) {
	if len(data) < UDPHeaderSize {
		return nil, ErrPacketTooShort
	}

	return &UDPHeader{
		SrcPort:  binary.BigEndian.Uint16(data[0:2]),
		DstPort:  binary.BigEndian.Uint16(data[2:4]),
		Length:   binary.BigEndian.Uint16(data[4:6]),
		Checksum: binary.BigEndian.Uint16(data[6:8]),
	}, nil
}

// Serialize writes the UDP header to a byte slice.
func (h *UDPHeader) Serialize(data []byte) error {
	if len(data) < UDPHeaderSize {
		return ErrBufferTooSmall
	}

	binary.BigEndian.PutUint16(data[0:2], h.SrcPort)
	binary.BigEndian.PutUint16(data[2:4], h.DstPort)
	binary.BigEndian.PutUint16(data[4:6], h.Length)
	binary.BigEndian.PutUint16(data[6:8], h.Checksum)

	return nil
}

// TCPHeader represents a TCP packet header (minimal, without options).
type TCPHeader struct {
	SrcPort    uint16
	DstPort    uint16
	SeqNum     uint32
	AckNum     uint32
	DataOffset uint8
	Flags      uint8
	Window     uint16
	Checksum   uint16
	UrgentPtr  uint16
}

// TCP flag constants
const (
	TCPFlagFIN = 0x01
	TCPFlagSYN = 0x02
	TCPFlagRST = 0x04
	TCPFlagPSH = 0x08
	TCPFlagACK = 0x10
	TCPFlagURG = 0x20
)

// ParseTCPHeader parses a TCP header from a byte slice.
func ParseTCPHeader(data []byte) (*TCPHeader, error) {
	if len(data) < TCPMinHeaderSize {
		return nil, ErrPacketTooShort
	}

	dataOffset := (data[12] >> 4) * 4

	return &TCPHeader{
		SrcPort:    binary.BigEndian.Uint16(data[0:2]),
		DstPort:    binary.BigEndian.Uint16(data[2:4]),
		SeqNum:     binary.BigEndian.Uint32(data[4:8]),
		AckNum:     binary.BigEndian.Uint32(data[8:12]),
		DataOffset: dataOffset,
		Flags:      data[13],
		Window:     binary.BigEndian.Uint16(data[14:16]),
		Checksum:   binary.BigEndian.Uint16(data[16:18]),
		UrgentPtr:  binary.BigEndian.Uint16(data[18:20]),
	}, nil
}

// Packet errors
var (
	ErrPacketTooShort  = packetError("packet too short")
	ErrInvalidPacket   = packetError("invalid packet")
	ErrBufferTooSmall  = packetError("buffer too small")
	ErrUnsupportedType = packetError("unsupported packet type")
)

type packetError string

func (e packetError) Error() string {
	return string(e)
}

// calculateIPChecksum calculates the IPv4 header checksum.
func calculateIPChecksum(header []byte) uint16 {
	length := len(header)
	var sum uint32

	for i := 0; i < length-1; i += 2 {
		sum += uint32(binary.BigEndian.Uint16(header[i : i+2]))
	}

	// Handle odd length
	if length%2 == 1 {
		sum += uint32(header[length-1]) << 8
	}

	// Fold 32-bit sum to 16 bits
	for sum > 0xFFFF {
		sum = (sum & 0xFFFF) + (sum >> 16)
	}

	return ^uint16(sum)
}

// PacketProcessor provides a pipeline for processing packets.
type PacketProcessor struct {
	handlers []PacketHandler
}

// PacketHandler is a function that processes a packet.
// Returns true to continue processing, false to stop.
type PacketHandler func(data []byte) ([]byte, bool)

// NewPacketProcessor creates a new packet processor.
func NewPacketProcessor() *PacketProcessor {
	return &PacketProcessor{
		handlers: make([]PacketHandler, 0),
	}
}

// AddHandler adds a handler to the processing pipeline.
func (p *PacketProcessor) AddHandler(h PacketHandler) {
	p.handlers = append(p.handlers, h)
}

// Process runs a packet through the processing pipeline.
func (p *PacketProcessor) Process(data []byte) ([]byte, bool) {
	result := data
	for _, handler := range p.handlers {
		var cont bool
		result, cont = handler(result)
		if !cont {
			return result, false
		}
	}
	return result, true
}
