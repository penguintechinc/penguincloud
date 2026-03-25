// Package memory provides memory pool management for zero-copy operations.
package memory

import (
	"errors"
	"sync"
	"sync/atomic"
)

var (
	// ErrPoolExhausted is returned when no slots are available.
	ErrPoolExhausted = errors.New("memory pool exhausted")
	// ErrInvalidSlot is returned when an invalid slot index is used.
	ErrInvalidSlot = errors.New("invalid slot index")
	// ErrSlotNotInUse is returned when trying to release an unused slot.
	ErrSlotNotInUse = errors.New("slot not in use")
)

// MemoryPool provides pre-allocated memory slots for zero-copy operations.
type MemoryPool struct {
	allocator *NUMAAllocator
	data      []byte        // Contiguous memory region
	slotSize  int           // Size of each slot
	numSlots  int           // Total number of slots
	freeList  chan int      // Channel of free slot indices
	inUse     []atomic.Bool // Track which slots are in use

	// Statistics
	totalAllocs   atomic.Uint64
	totalFrees    atomic.Uint64
	peakUsage     atomic.Int32
	currentUsage  atomic.Int32

	mu sync.RWMutex
}

// PoolConfig holds configuration for memory pool.
type PoolConfig struct {
	NumSlots     int
	SlotSize     int
	NUMANodeID   int
	UseHugepages bool
	Preallocate  bool
}

// DefaultPoolConfig returns sensible defaults for a memory pool.
func DefaultPoolConfig() PoolConfig {
	return PoolConfig{
		NumSlots:     4096,
		SlotSize:     2048, // Typical MTU size
		NUMANodeID:   0,
		UseHugepages: false,
		Preallocate:  true,
	}
}

// NewMemoryPool creates a new pre-allocated memory pool.
func NewMemoryPool(config PoolConfig) (*MemoryPool, error) {
	allocator, err := NewNUMAAllocator(config.NUMANodeID, config.UseHugepages)
	if err != nil {
		return nil, err
	}

	totalSize := config.NumSlots * config.SlotSize

	// Allocate contiguous memory region
	var data []byte
	if config.Preallocate {
		data, err = allocator.AllocateAligned(totalSize)
		if err != nil {
			return nil, err
		}

		// Touch all pages to ensure they're allocated
		for i := 0; i < totalSize; i += 4096 {
			data[i] = 0
		}
	}

	pool := &MemoryPool{
		allocator: allocator,
		data:      data,
		slotSize:  config.SlotSize,
		numSlots:  config.NumSlots,
		freeList:  make(chan int, config.NumSlots),
		inUse:     make([]atomic.Bool, config.NumSlots),
	}

	// Initialize free list with all slot indices
	for i := 0; i < config.NumSlots; i++ {
		pool.freeList <- i
	}

	return pool, nil
}

// Acquire gets a free memory slot from the pool.
// Returns the slot index and a byte slice for the slot.
func (p *MemoryPool) Acquire() (int, []byte, error) {
	select {
	case idx := <-p.freeList:
		// Mark slot as in use
		if !p.inUse[idx].CompareAndSwap(false, true) {
			// Slot was already in use (shouldn't happen)
			return 0, nil, ErrInvalidSlot
		}

		// Update statistics
		p.totalAllocs.Add(1)
		current := p.currentUsage.Add(1)

		// Update peak usage
		for {
			peak := p.peakUsage.Load()
			if current <= peak || p.peakUsage.CompareAndSwap(peak, current) {
				break
			}
		}

		// Return slice pointing to slot in contiguous memory
		start := idx * p.slotSize
		end := start + p.slotSize
		return idx, p.data[start:end], nil

	default:
		return 0, nil, ErrPoolExhausted
	}
}

// Release returns a slot to the pool.
func (p *MemoryPool) Release(idx int) error {
	if idx < 0 || idx >= p.numSlots {
		return ErrInvalidSlot
	}

	// Mark slot as not in use
	if !p.inUse[idx].CompareAndSwap(true, false) {
		return ErrSlotNotInUse
	}

	// Clear slot data (optional, for security)
	start := idx * p.slotSize
	end := start + p.slotSize
	for i := start; i < end; i++ {
		p.data[i] = 0
	}

	// Return to free list
	p.freeList <- idx

	// Update statistics
	p.totalFrees.Add(1)
	p.currentUsage.Add(-1)

	return nil
}

// GetSlot returns a byte slice for a slot without acquiring it.
// Used for reading data from a slot that's already acquired.
func (p *MemoryPool) GetSlot(idx int) ([]byte, error) {
	if idx < 0 || idx >= p.numSlots {
		return nil, ErrInvalidSlot
	}

	if !p.inUse[idx].Load() {
		return nil, ErrSlotNotInUse
	}

	start := idx * p.slotSize
	end := start + p.slotSize
	return p.data[start:end], nil
}

// Stats returns current pool statistics.
type PoolStats struct {
	TotalSlots   int
	FreeSlots    int
	UsedSlots    int
	TotalAllocs  uint64
	TotalFrees   uint64
	PeakUsage    int32
	SlotSize     int
	TotalMemory  int
}

// Stats returns current pool statistics.
func (p *MemoryPool) Stats() PoolStats {
	freeCount := len(p.freeList)
	return PoolStats{
		TotalSlots:  p.numSlots,
		FreeSlots:   freeCount,
		UsedSlots:   p.numSlots - freeCount,
		TotalAllocs: p.totalAllocs.Load(),
		TotalFrees:  p.totalFrees.Load(),
		PeakUsage:   p.peakUsage.Load(),
		SlotSize:    p.slotSize,
		TotalMemory: p.numSlots * p.slotSize,
	}
}

// Close releases all memory allocated by the pool.
func (p *MemoryPool) Close() error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.data != nil {
		if err := p.allocator.Free(p.data); err != nil {
			return err
		}
		p.data = nil
	}

	close(p.freeList)
	return nil
}
