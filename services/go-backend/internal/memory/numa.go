// Package memory provides NUMA-aware memory management.
package memory

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"

	"golang.org/x/sys/unix"
)

// NUMAInfo holds NUMA topology information.
type NUMAInfo struct {
	NodeCount    int
	CurrentNode  int
	CPUsPerNode  map[int][]int
	MemoryMB     map[int]int64
	Available    bool
}

// NUMAAllocator provides NUMA-aware memory allocation.
type NUMAAllocator struct {
	nodeID       int
	hugepages    bool
	initialized  bool
}

// NewNUMAAllocator creates a new NUMA-aware allocator.
func NewNUMAAllocator(nodeID int, useHugepages bool) (*NUMAAllocator, error) {
	allocator := &NUMAAllocator{
		nodeID:    nodeID,
		hugepages: useHugepages,
	}

	// Verify NUMA is available
	info := GetNUMAInfo()
	if !info.Available {
		return allocator, nil // Return allocator but NUMA won't be used
	}

	if nodeID >= info.NodeCount {
		return nil, fmt.Errorf("NUMA node %d does not exist (max: %d)", nodeID, info.NodeCount-1)
	}

	allocator.initialized = true
	return allocator, nil
}

// BindToNode binds the current goroutine/thread to a specific NUMA node.
func (a *NUMAAllocator) BindToNode() error {
	if !a.initialized {
		return nil // NUMA not available, skip binding
	}

	// Lock OS thread to ensure affinity is applied
	runtime.LockOSThread()

	info := GetNUMAInfo()
	cpus, ok := info.CPUsPerNode[a.nodeID]
	if !ok || len(cpus) == 0 {
		return fmt.Errorf("no CPUs found for NUMA node %d", a.nodeID)
	}

	// Set CPU affinity to CPUs on this NUMA node
	var cpuSet unix.CPUSet
	for _, cpu := range cpus {
		cpuSet.Set(cpu)
	}

	return unix.SchedSetaffinity(0, &cpuSet)
}

// AllocateAligned allocates page-aligned memory, optionally using hugepages.
func (a *NUMAAllocator) AllocateAligned(size int) ([]byte, error) {
	pageSize := os.Getpagesize()

	// Round up to page size
	alignedSize := ((size + pageSize - 1) / pageSize) * pageSize

	flags := syscall.MAP_PRIVATE | syscall.MAP_ANONYMOUS

	if a.hugepages {
		flags |= syscall.MAP_HUGETLB
	}

	// Use mmap for page-aligned allocation
	data, err := unix.Mmap(-1, 0, alignedSize, syscall.PROT_READ|syscall.PROT_WRITE, flags)
	if err != nil {
		// Fallback to regular allocation if hugepages fail
		if a.hugepages {
			flags &^= syscall.MAP_HUGETLB
			data, err = unix.Mmap(-1, 0, alignedSize, syscall.PROT_READ|syscall.PROT_WRITE, flags)
		}
		if err != nil {
			return nil, fmt.Errorf("mmap failed: %w", err)
		}
	}

	// Lock memory to prevent swapping (requires CAP_IPC_LOCK)
	if err := unix.Mlock(data); err != nil {
		// Non-fatal: memory will still work, just might be swapped
		// Log warning in production
	}

	return data, nil
}

// Free releases memory allocated with AllocateAligned.
func (a *NUMAAllocator) Free(data []byte) error {
	if len(data) == 0 {
		return nil
	}
	return unix.Munmap(data)
}

// GetNUMAInfo returns information about NUMA topology.
func GetNUMAInfo() NUMAInfo {
	info := NUMAInfo{
		CPUsPerNode: make(map[int][]int),
		MemoryMB:    make(map[int]int64),
	}

	// Check if NUMA is available
	numaPath := "/sys/devices/system/node"
	if _, err := os.Stat(numaPath); os.IsNotExist(err) {
		info.Available = false
		return info
	}

	// Count NUMA nodes
	entries, err := os.ReadDir(numaPath)
	if err != nil {
		info.Available = false
		return info
	}

	for _, entry := range entries {
		if !entry.IsDir() || !strings.HasPrefix(entry.Name(), "node") {
			continue
		}

		nodeIDStr := strings.TrimPrefix(entry.Name(), "node")
		nodeID, err := strconv.Atoi(nodeIDStr)
		if err != nil {
			continue
		}

		info.NodeCount++

		// Get CPUs for this node
		cpuListPath := filepath.Join(numaPath, entry.Name(), "cpulist")
		if cpuData, err := os.ReadFile(cpuListPath); err == nil {
			info.CPUsPerNode[nodeID] = parseCPUList(string(cpuData))
		}

		// Get memory for this node
		memInfoPath := filepath.Join(numaPath, entry.Name(), "meminfo")
		if memData, err := os.ReadFile(memInfoPath); err == nil {
			info.MemoryMB[nodeID] = parseNodeMemory(string(memData))
		}
	}

	info.Available = info.NodeCount > 0

	// Get current node (approximate based on current CPU)
	if info.Available {
		info.CurrentNode = getCurrentNUMANode(info)
	}

	return info
}

// parseCPUList parses a CPU list string like "0-3,8-11" into slice of CPU IDs.
func parseCPUList(cpuList string) []int {
	var cpus []int
	cpuList = strings.TrimSpace(cpuList)

	for _, part := range strings.Split(cpuList, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}

		if strings.Contains(part, "-") {
			// Range like "0-3"
			rangeParts := strings.Split(part, "-")
			if len(rangeParts) == 2 {
				start, _ := strconv.Atoi(rangeParts[0])
				end, _ := strconv.Atoi(rangeParts[1])
				for i := start; i <= end; i++ {
					cpus = append(cpus, i)
				}
			}
		} else {
			// Single CPU
			if cpu, err := strconv.Atoi(part); err == nil {
				cpus = append(cpus, cpu)
			}
		}
	}

	return cpus
}

// parseNodeMemory extracts total memory from NUMA node meminfo.
func parseNodeMemory(memInfo string) int64 {
	for _, line := range strings.Split(memInfo, "\n") {
		if strings.Contains(line, "MemTotal") {
			parts := strings.Fields(line)
			if len(parts) >= 4 {
				if kb, err := strconv.ParseInt(parts[3], 10, 64); err == nil {
					return kb / 1024 // Convert to MB
				}
			}
		}
	}
	return 0
}

// getCurrentNUMANode determines which NUMA node the current thread is on.
func getCurrentNUMANode(info NUMAInfo) int {
	// Get current CPU
	cpu := unix.SchedGetcpu()

	// Find which node this CPU belongs to
	for nodeID, cpus := range info.CPUsPerNode {
		for _, c := range cpus {
			if c == cpu {
				return nodeID
			}
		}
	}

	return 0
}
