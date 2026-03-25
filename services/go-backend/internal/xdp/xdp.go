// Package xdp provides XDP (eXpress Data Path) program management.
package xdp

import (
	"errors"
	"fmt"
	"net"
	"os"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/link"
	"golang.org/x/sys/unix"
)

// XDPMode represents the XDP attach mode.
type XDPMode int

const (
	// XDPModeUnspec lets the kernel choose the best mode.
	XDPModeUnspec XDPMode = iota
	// XDPModeSKB is the generic/slower mode that works everywhere.
	XDPModeSKB
	// XDPModeNative is the driver-level mode for supported NICs.
	XDPModeNative
	// XDPModeOffload offloads to NIC hardware (very limited support).
	XDPModeOffload
)

var (
	// ErrXDPNotSupported is returned when XDP is not available.
	ErrXDPNotSupported = errors.New("XDP not supported on this system")
	// ErrInterfaceNotFound is returned when the network interface doesn't exist.
	ErrInterfaceNotFound = errors.New("network interface not found")
)

// XDPProgram represents a loaded XDP program.
type XDPProgram struct {
	ifaceName string
	ifaceIdx  int
	mode      XDPMode
	link      link.Link
	prog      *ebpf.Program
}

// XDPConfig holds configuration for XDP program loading.
type XDPConfig struct {
	InterfaceName string
	Mode          XDPMode
	ProgramPath   string // Path to compiled eBPF object file
}

// ParseXDPMode parses a string mode to XDPMode.
func ParseXDPMode(mode string) XDPMode {
	switch mode {
	case "native", "drv":
		return XDPModeNative
	case "offload", "hw":
		return XDPModeOffload
	case "skb", "generic":
		return XDPModeSKB
	default:
		return XDPModeUnspec
	}
}

// IsXDPSupported checks if XDP is supported on this system.
func IsXDPSupported() bool {
	// Check for BPF filesystem
	if _, err := os.Stat("/sys/fs/bpf"); os.IsNotExist(err) {
		return false
	}

	// Check for CAP_BPF or CAP_SYS_ADMIN
	// In practice, we need to be root or have specific capabilities
	return os.Geteuid() == 0
}

// GetInterfaceIndex returns the index of a network interface.
func GetInterfaceIndex(name string) (int, error) {
	iface, err := net.InterfaceByName(name)
	if err != nil {
		return 0, fmt.Errorf("%w: %s", ErrInterfaceNotFound, name)
	}
	return iface.Index, nil
}

// LoadXDPProgram loads an XDP program from an eBPF object file.
// Note: This is a skeleton implementation. In production, you would
// compile actual eBPF C code and load it here.
func LoadXDPProgram(config XDPConfig) (*XDPProgram, error) {
	if !IsXDPSupported() {
		return nil, ErrXDPNotSupported
	}

	ifaceIdx, err := GetInterfaceIndex(config.InterfaceName)
	if err != nil {
		return nil, err
	}

	xdp := &XDPProgram{
		ifaceName: config.InterfaceName,
		ifaceIdx:  ifaceIdx,
		mode:      config.Mode,
	}

	// In a real implementation, you would:
	// 1. Load the eBPF object file
	// 2. Get the XDP program from the collection
	// 3. Attach it to the interface
	//
	// Example with a real program:
	// spec, err := ebpf.LoadCollectionSpec(config.ProgramPath)
	// coll, err := ebpf.NewCollection(spec)
	// xdp.prog = coll.Programs["xdp_prog"]
	// xdp.link, err = link.AttachXDP(link.XDPOptions{...})

	return xdp, nil
}

// Detach removes the XDP program from the interface.
func (x *XDPProgram) Detach() error {
	if x.link != nil {
		return x.link.Close()
	}
	return nil
}

// InterfaceName returns the interface name.
func (x *XDPProgram) InterfaceName() string {
	return x.ifaceName
}

// InterfaceIndex returns the interface index.
func (x *XDPProgram) InterfaceIndex() int {
	return x.ifaceIdx
}

// Mode returns the XDP mode.
func (x *XDPProgram) Mode() XDPMode {
	return x.mode
}

// XDPAction represents an XDP program action.
type XDPAction int

const (
	// XDPAborted indicates an error occurred.
	XDPAborted XDPAction = iota
	// XDPDrop drops the packet.
	XDPDrop
	// XDPPass passes the packet to the normal network stack.
	XDPPass
	// XDPTX transmits the packet back out the same interface.
	XDPTX
	// XDPRedirect redirects the packet to another interface or CPU.
	XDPRedirect
)

// String returns the string representation of an XDPAction.
func (a XDPAction) String() string {
	switch a {
	case XDPAborted:
		return "XDP_ABORTED"
	case XDPDrop:
		return "XDP_DROP"
	case XDPPass:
		return "XDP_PASS"
	case XDPTX:
		return "XDP_TX"
	case XDPRedirect:
		return "XDP_REDIRECT"
	default:
		return "UNKNOWN"
	}
}

// GetXDPStats retrieves XDP statistics from the kernel.
type XDPStats struct {
	RxPackets  uint64
	RxBytes    uint64
	TxPackets  uint64
	TxBytes    uint64
	Drops      uint64
	Errors     uint64
}

// GetInterfaceStats gets network interface statistics.
func GetInterfaceStats(ifaceName string) (*XDPStats, error) {
	iface, err := net.InterfaceByName(ifaceName)
	if err != nil {
		return nil, err
	}

	// Read stats from /sys/class/net/<iface>/statistics/
	basePath := fmt.Sprintf("/sys/class/net/%s/statistics", iface.Name)

	stats := &XDPStats{}

	if rx, err := readStatFile(basePath + "/rx_packets"); err == nil {
		stats.RxPackets = rx
	}
	if rx, err := readStatFile(basePath + "/rx_bytes"); err == nil {
		stats.RxBytes = rx
	}
	if tx, err := readStatFile(basePath + "/tx_packets"); err == nil {
		stats.TxPackets = tx
	}
	if tx, err := readStatFile(basePath + "/tx_bytes"); err == nil {
		stats.TxBytes = tx
	}
	if drops, err := readStatFile(basePath + "/rx_dropped"); err == nil {
		stats.Drops = drops
	}
	if errs, err := readStatFile(basePath + "/rx_errors"); err == nil {
		stats.Errors = errs
	}

	return stats, nil
}

func readStatFile(path string) (uint64, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return 0, err
	}

	var value uint64
	_, err = fmt.Sscanf(string(data), "%d", &value)
	return value, err
}

// SetRLimitMemlock sets the memlock rlimit to allow BPF map creation.
func SetRLimitMemlock() error {
	return unix.Setrlimit(unix.RLIMIT_MEMLOCK, &unix.Rlimit{
		Cur: unix.RLIM_INFINITY,
		Max: unix.RLIM_INFINITY,
	})
}
