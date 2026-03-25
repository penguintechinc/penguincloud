// Package memory provides buffer management for network operations.
package memory

import (
	"encoding/binary"
	"sync"
)

// Buffer provides a wrapper around a memory pool slot with helper methods.
type Buffer struct {
	pool    *MemoryPool
	slotIdx int
	data    []byte
	length  int // Actual data length (may be less than slot size)
}

// BufferPool manages a set of reusable buffers.
type BufferPool struct {
	memPool *MemoryPool
	buffers sync.Pool
}

// NewBufferPool creates a buffer pool backed by a memory pool.
func NewBufferPool(memPool *MemoryPool) *BufferPool {
	return &BufferPool{
		memPool: memPool,
		buffers: sync.Pool{
			New: func() interface{} {
				return &Buffer{}
			},
		},
	}
}

// Get acquires a buffer from the pool.
func (bp *BufferPool) Get() (*Buffer, error) {
	idx, data, err := bp.memPool.Acquire()
	if err != nil {
		return nil, err
	}

	buf := bp.buffers.Get().(*Buffer)
	buf.pool = bp.memPool
	buf.slotIdx = idx
	buf.data = data
	buf.length = 0

	return buf, nil
}

// Put returns a buffer to the pool.
func (bp *BufferPool) Put(buf *Buffer) error {
	if buf == nil {
		return nil
	}

	err := bp.memPool.Release(buf.slotIdx)
	if err != nil {
		return err
	}

	// Clear buffer metadata
	buf.pool = nil
	buf.data = nil
	buf.length = 0

	bp.buffers.Put(buf)
	return nil
}

// Data returns the underlying byte slice up to the current length.
func (b *Buffer) Data() []byte {
	return b.data[:b.length]
}

// RawData returns the full underlying byte slice (slot size).
func (b *Buffer) RawData() []byte {
	return b.data
}

// Length returns the current data length.
func (b *Buffer) Length() int {
	return b.length
}

// Capacity returns the maximum capacity (slot size).
func (b *Buffer) Capacity() int {
	return len(b.data)
}

// SetLength sets the current data length.
func (b *Buffer) SetLength(n int) {
	if n > len(b.data) {
		n = len(b.data)
	}
	b.length = n
}

// Reset clears the buffer.
func (b *Buffer) Reset() {
	b.length = 0
}

// Write appends data to the buffer.
func (b *Buffer) Write(p []byte) (n int, err error) {
	available := len(b.data) - b.length
	if len(p) > available {
		p = p[:available]
	}

	copy(b.data[b.length:], p)
	b.length += len(p)
	return len(p), nil
}

// Read reads data from the buffer.
func (b *Buffer) Read(p []byte) (n int, err error) {
	if b.length == 0 {
		return 0, nil
	}

	n = copy(p, b.data[:b.length])
	return n, nil
}

// WriteUint16 writes a uint16 in network byte order.
func (b *Buffer) WriteUint16(v uint16) error {
	if b.length+2 > len(b.data) {
		return ErrPoolExhausted
	}
	binary.BigEndian.PutUint16(b.data[b.length:], v)
	b.length += 2
	return nil
}

// WriteUint32 writes a uint32 in network byte order.
func (b *Buffer) WriteUint32(v uint32) error {
	if b.length+4 > len(b.data) {
		return ErrPoolExhausted
	}
	binary.BigEndian.PutUint32(b.data[b.length:], v)
	b.length += 4
	return nil
}

// ReadUint16At reads a uint16 at the specified offset.
func (b *Buffer) ReadUint16At(offset int) uint16 {
	if offset+2 > b.length {
		return 0
	}
	return binary.BigEndian.Uint16(b.data[offset:])
}

// ReadUint32At reads a uint32 at the specified offset.
func (b *Buffer) ReadUint32At(offset int) uint32 {
	if offset+4 > b.length {
		return 0
	}
	return binary.BigEndian.Uint32(b.data[offset:])
}

// SlotIndex returns the underlying memory pool slot index.
func (b *Buffer) SlotIndex() int {
	return b.slotIdx
}
