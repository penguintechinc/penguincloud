// Package xdp provides AF_XDP socket management for zero-copy packet processing.
package xdp

import (
	"errors"
	"fmt"
	"sync"
	"unsafe"

	"golang.org/x/sys/unix"
)

var (
	// ErrSocketCreation is returned when socket creation fails.
	ErrSocketCreation = errors.New("failed to create AF_XDP socket")
	// ErrUMEMSetup is returned when UMEM setup fails.
	ErrUMEMSetup = errors.New("failed to setup UMEM")
	// ErrRingSetup is returned when ring buffer setup fails.
	ErrRingSetup = errors.New("failed to setup ring buffers")
)

// AF_XDP socket constants
const (
	// SOL_XDP is the socket option level for XDP.
	SOL_XDP = 283

	// XDP socket options
	XDP_MMAP_OFFSETS     = 1
	XDP_RX_RING          = 2
	XDP_TX_RING          = 3
	XDP_UMEM_REG         = 4
	XDP_UMEM_FILL_RING   = 5
	XDP_UMEM_COMPLETION_RING = 6
	XDP_STATISTICS       = 7

	// XDP bind flags
	XDP_SHARED_UMEM = 1 << 0
	XDP_COPY        = 1 << 1
	XDP_ZEROCOPY    = 1 << 2
)

// XDPSocketConfig holds configuration for an AF_XDP socket.
type XDPSocketConfig struct {
	InterfaceName string
	QueueID       int
	NumFrames     int
	FrameSize     int
	RxRingSize    int
	TxRingSize    int
	FillRingSize  int
	CompRingSize  int
	ZeroCopy      bool
}

// DefaultSocketConfig returns sensible defaults for AF_XDP socket.
func DefaultSocketConfig(ifaceName string) XDPSocketConfig {
	return XDPSocketConfig{
		InterfaceName: ifaceName,
		QueueID:       0,
		NumFrames:     4096,
		FrameSize:     2048,
		RxRingSize:    2048,
		TxRingSize:    2048,
		FillRingSize:  2048,
		CompRingSize:  2048,
		ZeroCopy:      false, // Start with copy mode for compatibility
	}
}

// UMEM represents the shared memory region for AF_XDP.
type UMEM struct {
	data      []byte
	numFrames int
	frameSize int
	headroom  int
}

// XDPRing represents a ring buffer for AF_XDP.
type XDPRing struct {
	producer *uint32
	consumer *uint32
	desc     unsafe.Pointer
	mask     uint32
	size     uint32
	cached   uint32
}

// XDPSocket represents an AF_XDP socket for high-performance packet I/O.
type XDPSocket struct {
	fd         int
	ifaceIdx   int
	queueID    int
	umem       *UMEM
	rxRing     *XDPRing
	txRing     *XDPRing
	fillRing   *XDPRing
	compRing   *XDPRing
	config     XDPSocketConfig

	rxChan chan []byte
	txChan chan []byte

	mu     sync.Mutex
	closed bool
}

// NewXDPSocket creates a new AF_XDP socket.
// Note: This requires CAP_NET_ADMIN and CAP_SYS_ADMIN capabilities.
func NewXDPSocket(config XDPSocketConfig) (*XDPSocket, error) {
	ifaceIdx, err := GetInterfaceIndex(config.InterfaceName)
	if err != nil {
		return nil, err
	}

	// Create AF_XDP socket
	fd, err := unix.Socket(unix.AF_XDP, unix.SOCK_RAW, 0)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrSocketCreation, err)
	}

	sock := &XDPSocket{
		fd:       fd,
		ifaceIdx: ifaceIdx,
		queueID:  config.QueueID,
		config:   config,
		rxChan:   make(chan []byte, config.RxRingSize),
		txChan:   make(chan []byte, config.TxRingSize),
	}

	// Setup UMEM
	if err := sock.setupUMEM(); err != nil {
		unix.Close(fd)
		return nil, err
	}

	// Setup ring buffers
	if err := sock.setupRings(); err != nil {
		sock.Close()
		return nil, err
	}

	// Bind socket to interface and queue
	if err := sock.bind(); err != nil {
		sock.Close()
		return nil, err
	}

	return sock, nil
}

// setupUMEM allocates and registers the UMEM region.
func (s *XDPSocket) setupUMEM() error {
	totalSize := s.config.NumFrames * s.config.FrameSize

	// Allocate page-aligned memory
	data, err := unix.Mmap(-1, 0, totalSize,
		unix.PROT_READ|unix.PROT_WRITE,
		unix.MAP_PRIVATE|unix.MAP_ANONYMOUS)
	if err != nil {
		return fmt.Errorf("%w: mmap failed: %v", ErrUMEMSetup, err)
	}

	// Lock memory to prevent swapping
	if err := unix.Mlock(data); err != nil {
		// Non-fatal, continue anyway
	}

	s.umem = &UMEM{
		data:      data,
		numFrames: s.config.NumFrames,
		frameSize: s.config.FrameSize,
	}

	// Register UMEM with kernel
	// This would use the XDP_UMEM_REG socket option
	// Omitted for brevity - requires struct definitions matching kernel

	return nil
}

// setupRings configures the ring buffers.
func (s *XDPSocket) setupRings() error {
	// Ring buffer setup requires mmap of specific offsets
	// This is a simplified skeleton - full implementation requires
	// kernel struct definitions and mmap calls

	s.rxRing = &XDPRing{
		size: uint32(s.config.RxRingSize),
		mask: uint32(s.config.RxRingSize - 1),
	}
	s.txRing = &XDPRing{
		size: uint32(s.config.TxRingSize),
		mask: uint32(s.config.TxRingSize - 1),
	}
	s.fillRing = &XDPRing{
		size: uint32(s.config.FillRingSize),
		mask: uint32(s.config.FillRingSize - 1),
	}
	s.compRing = &XDPRing{
		size: uint32(s.config.CompRingSize),
		mask: uint32(s.config.CompRingSize - 1),
	}

	return nil
}

// bind binds the socket to an interface and queue.
func (s *XDPSocket) bind() error {
	sa := &unix.SockaddrXDP{
		Flags:   0,
		Ifindex: uint32(s.ifaceIdx),
		QueueID: uint32(s.queueID),
	}

	if s.config.ZeroCopy {
		sa.Flags |= XDP_ZEROCOPY
	} else {
		sa.Flags |= XDP_COPY
	}

	return unix.Bind(s.fd, sa)
}

// Receive receives a packet from the socket.
// Returns the packet data and the frame index (for returning to fill ring).
func (s *XDPSocket) Receive() ([]byte, int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return nil, 0, errors.New("socket closed")
	}

	// Poll for data
	pollFds := []unix.PollFd{{
		Fd:     int32(s.fd),
		Events: unix.POLLIN,
	}}

	n, err := unix.Poll(pollFds, 1000) // 1 second timeout
	if err != nil {
		return nil, 0, err
	}

	if n == 0 {
		return nil, 0, nil // Timeout, no data
	}

	// In a real implementation, we would:
	// 1. Read from the RX ring
	// 2. Get the frame descriptor
	// 3. Return the data slice and frame index

	return nil, 0, nil
}

// Send sends a packet through the socket.
func (s *XDPSocket) Send(data []byte) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return errors.New("socket closed")
	}

	if len(data) > s.config.FrameSize {
		return errors.New("packet too large")
	}

	// In a real implementation, we would:
	// 1. Get a frame from the completion ring
	// 2. Copy data to the frame
	// 3. Add to TX ring
	// 4. Kick the kernel to send

	return nil
}

// ReturnFrame returns a frame to the fill ring after processing.
func (s *XDPSocket) ReturnFrame(frameIdx int) error {
	// Add frame index to fill ring so kernel can use it for new packets
	return nil
}

// Stats returns socket statistics.
type XDPSocketStats struct {
	RxDropped    uint64
	RxInvalid    uint64
	TxInvalid    uint64
	RxRingFull   uint64
	FillRingFull uint64
	TxRingFull   uint64
}

// Stats retrieves socket statistics.
func (s *XDPSocket) Stats() (*XDPSocketStats, error) {
	// Use getsockopt with XDP_STATISTICS
	return &XDPSocketStats{}, nil
}

// FileDescriptor returns the socket file descriptor.
func (s *XDPSocket) FileDescriptor() int {
	return s.fd
}

// Close closes the socket and releases resources.
func (s *XDPSocket) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return nil
	}
	s.closed = true

	close(s.rxChan)
	close(s.txChan)

	// Unmap UMEM
	if s.umem != nil && s.umem.data != nil {
		unix.Munmap(s.umem.data)
	}

	return unix.Close(s.fd)
}
