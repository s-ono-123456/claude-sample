package com.example.testsampleapp.dao;

import com.example.testsampleapp.model.Product;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ProductDao {
    Product findById(Integer id);
}
