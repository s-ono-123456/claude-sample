package com.example.sampleapp.dao;

import com.example.sampleapp.model.Product;
import org.apache.ibatis.annotations.Mapper;
import java.util.List;

@Mapper
public interface ProductDao {
    List<Product> findAll();
    List<Product> findByCategory(String category);
    Product findById(Integer id);
    int insert(Product product);
    int update(Product product);
    int delete(Integer id);
    int updateStock(Integer id, Integer quantity);
}
